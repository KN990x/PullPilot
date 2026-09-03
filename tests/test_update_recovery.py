"""Recovery after a failed update.

Two things were broken and neither had a test. With a moving tag (`:latest`, the homelab
norm) `compose pull` overwrites what the tag points at, so reverting only the compose file
redeployed the very image that had just broken. And a stack with no Git repo got no
recovery at all: `compose stop` had already run, so a failed `up` left it down.

The fake below models the part of Docker that matters here: a tag table that `compose
pull` mutates, so a test can tell a real revert from a no-op.
"""

import json

import pytest
import server.services.projects as projects_module
from fastapi.testclient import TestClient
from server.database import session_scope
from server.models.db import ProjectSettings
from server.services.docker import COMPOSE_CMD
from server.services.projects import update_single_project_logic

OLD_NGINX = "sha256:old-nginx"
OLD_REDIS = "sha256:old-redis"
NEW_NGINX = "sha256:new-nginx"
NEW_REDIS = "sha256:new-redis"


class FakeDocker:
    """Records every command and answers the ones the update flow issues."""

    def __init__(self, *, images: dict[str, str], fail_on: str | None = None) -> None:
        self.images = dict(images)
        self.fail_on = fail_on
        self.calls: list[str] = []
        self._failed_once = False

    def __call__(self, cmd, cwd=None, *, log_exec=True, log_errors=True, locale="es"):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        self.calls.append(text)

        if text == f"{COMPOSE_CMD} config --images":
            return "nginx:latest\nredis:7\nnever-pulled:1\n"

        if text.startswith("docker image inspect"):
            ref = text.rsplit(" ", 1)[1]
            if ref not in self.images:
                raise RuntimeError(f"No such image: {ref}")
            return self.images[ref]

        if text.startswith("docker tag "):
            _, _, image_id, ref = text.split(" ")
            self.images[ref] = image_id
            return ""

        if text == f"{COMPOSE_CMD} pull":
            # What breaks a naive rollback: the tag now names a different image.
            self.images["nginx:latest"] = NEW_NGINX
            self.images["redis:7"] = NEW_REDIS
            return ""

        # Only the first deploy fails; the recovery redeploy has to be able to succeed.
        if self.fail_on and text == self.fail_on and not self._failed_once:
            self._failed_once = True
            raise RuntimeError("boom: deploy failed")

        if "rev-parse HEAD" in text:
            return "abc1234def5678"

        # Healthcheck: two containers, running, with no healthcheck of their own.
        if text == f"{COMPOSE_CMD} ps -q":
            return "container1\ncontainer2\n"

        if text.startswith("docker inspect "):
            # One entry per requested ID, in order, the way `docker inspect` answers.
            ids = text.split()[2:]
            return json.dumps([{"State": {"Status": "running"}} for _ in ids])

        return ""

    def ran(self, prefix: str) -> list[str]:
        return [c for c in self.calls if c.startswith(prefix)]

    def git_ran(self, *needles: str) -> list[str]:
        return [c for c in self.calls if c.startswith("git ") and all(n in c for n in needles)]


UP_CMD = f"{COMPOSE_CMD} up -d --build --remove-orphans"


@pytest.fixture()
def stack(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path):
    """A registered project under the stacks root. `client` is what creates the schema."""
    root = tmp_path / "stacks"
    proj = root / "myapp"
    proj.mkdir(parents=True)
    (proj / "docker-compose.yml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setattr(projects_module, "PROJECTS_ROOT", root)

    with session_scope() as db:
        db.add(ProjectSettings(name="myapp", path=str(proj)))
        db.commit()
    yield proj
    with session_scope() as db:
        db.query(ProjectSettings).delete()
        db.commit()


def _run(fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> tuple[bool, list[str]]:
    monkeypatch.setattr(projects_module, "run_command", fake)
    with session_scope() as db:
        return update_single_project_logic("myapp", db, locale="en")


def test_snapshot_skips_images_that_are_not_local_yet(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    monkeypatch.setattr(projects_module, "run_command", fake)

    snapshot = projects_module.snapshot_stack_images(str(stack), locale="en")

    # `never-pulled:1` is declared by the stack but has no local image: not recoverable.
    assert snapshot == {"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}


def test_failed_deploy_restores_the_previous_images(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )

    success, logs = _run(fake, monkeypatch)

    assert success is False
    # The whole point: the tags name the old images again, not what the pull brought in.
    assert fake.images["nginx:latest"] == OLD_NGINX
    assert fake.images["redis:7"] == OLD_REDIS
    assert any("previous version" in line for line in logs)


def test_a_stack_without_git_is_still_brought_back_up(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`compose stop` already ran, so giving up here used to leave the stack down."""
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )

    success, _ = _run(fake, monkeypatch)

    assert success is False
    assert not fake.git_ran("reset"), "there is no repo here, nothing to reset"
    # Two `up`: the one that failed and the recovery one.
    assert len(fake.ran(UP_CMD)) == 2


def test_a_git_stack_reverts_code_and_images(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    (stack / ".git").mkdir()
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )

    success, _ = _run(fake, monkeypatch)

    assert success is False
    assert fake.git_ran("reset --hard", "abc1234def5678")
    assert fake.git_ran("safe.directory=")
    assert fake.images["nginx:latest"] == OLD_NGINX
    assert len(fake.ran(UP_CMD)) == 2


def test_recovery_runs_even_with_nothing_to_revert(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No repo and no image ever pulled locally: still try to leave the stack running."""
    fake = FakeDocker(images={}, fail_on=UP_CMD)

    success, logs = _run(fake, monkeypatch)

    assert success is False
    assert not fake.ran("docker tag")
    assert len(fake.ran(UP_CMD)) == 2
    assert any("Nothing to revert" in line for line in logs)


def test_a_failing_tag_does_not_stop_the_redeploy(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )
    original = fake.__call__

    def refuse_to_tag(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker tag "):
            fake.calls.append(text)
            raise RuntimeError("daemon says no")
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", refuse_to_tag)
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is False
    assert any("Could not revert image" in line for line in logs)
    assert len(fake.ran(UP_CMD)) == 2, "the redeploy must still be attempted"


def test_a_successful_update_never_reverts_anything(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})

    success, _ = _run(fake, monkeypatch)

    assert success is True
    assert not fake.ran("docker tag")
    assert fake.images["nginx:latest"] == NEW_NGINX


def test_a_one_shot_container_that_exited_cleanly_does_not_block_the_healthcheck(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An init/migration container has no healthcheck and ends `exited` with code 0.

    It is never going to be "running", so the health loop could not converge: it ran to
    the timeout and the timeout rolled back a deploy that had actually worked.
    """
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def with_a_one_shot(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker inspect "):
            fake.calls.append(text)
            return json.dumps(
                [
                    {"State": {"Status": "running"}},
                    {"State": {"Status": "exited", "ExitCode": 0}},
                ]
            )
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", with_a_one_shot)
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is True, logs
    assert len(fake.ran(UP_CMD)) == 1, "no rollback redeploy should have happened"


def test_a_stack_of_only_one_shots_is_healthy(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backup/certbot/migration stacks have nothing in `ps -q` once the job exits.

    The health loop used `ps -q` only, waited 5 s, raised `health.no_containers` and
    rolled back — which re-ran the one-shot.
    """
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def only_one_shots(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text == f"{COMPOSE_CMD} ps -q":
            fake.calls.append(text)
            return ""
        if text == f"{COMPOSE_CMD} ps -a -q":
            fake.calls.append(text)
            return "oneshot1\n"
        if text.startswith("docker inspect "):
            fake.calls.append(text)
            return json.dumps([{"State": {"Status": "exited", "ExitCode": 0}}])
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", only_one_shots)
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is True, logs
    assert len(fake.ran(UP_CMD)) == 1, "a successful one-shot stack must not be redeployed"


def test_git_invocations_set_safe_directory(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind-mounted clones are owned by the host user; Git 2.35+ refuses them otherwise."""
    (stack / ".git").mkdir()
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})

    success, _ = _run(fake, monkeypatch)

    assert success is True
    workdir = str(stack.resolve())
    pin = f"safe.directory={workdir}"
    assert fake.git_ran(pin, "rev-parse")
    assert fake.git_ran(pin, "status --porcelain")
    assert fake.git_ran(pin, "pull")


def test_a_one_shot_container_that_exited_with_an_error_still_fails(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def with_a_crash(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker inspect "):
            fake.calls.append(text)
            return json.dumps([{"State": {"Status": "exited", "ExitCode": 1}}] * 2)
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", with_a_crash)
    with session_scope() as db:
        success, _ = update_single_project_logic("myapp", db, locale="en")

    assert success is False


def test_a_dirty_git_tree_is_never_reset_hard(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git reset --hard` in the rollback deletes uncommitted compose/.env edits."""
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )
    (stack / ".git").mkdir()
    original = fake.__call__

    def dirty_tree(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if "status --porcelain" in text:
            fake.calls.append(text)
            return " M docker-compose.yml\n"
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", dirty_tree)
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is False
    assert not fake.git_ran("reset"), "uncommitted work would have been destroyed"
    assert any("uncommitted" in line for line in logs)
    assert len(fake.ran(UP_CMD)) == 2, "the stack must still be brought back up"


def test_a_clean_git_tree_is_reset_on_failure(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(
        images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS}, fail_on=UP_CMD
    )
    (stack / ".git").mkdir()

    success, _ = _run(fake, monkeypatch)

    assert success is False
    assert fake.git_ran("reset --hard", "abc1234def5678")


@pytest.mark.parametrize(
    ("state", "fragment"),
    [
        ({"Status": "restarting"}, "restart"),
        ({"Status": "running", "Health": {"Status": "unhealthy"}}, "unhealthy"),
    ],
)
def test_the_healthcheck_rejects_a_broken_container(
    stack, monkeypatch: pytest.MonkeyPatch, state: dict, fragment: str
) -> None:
    """Each of these raises its own RuntimeError and none of them had a test."""
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def with_state(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker inspect "):
            fake.calls.append(text)
            return json.dumps([{"State": state}] * 2)
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", with_state)
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is False
    assert any(fragment in line.lower() for line in logs)
    assert len(fake.ran(UP_CMD)) == 2, "the rollback redeploy must still run"


class FakeClock:
    """`time` for the health loop: sleeping advances the clock instead of the wall.

    The loop waits real seconds before giving up, which is correct in production and pure
    dead time in a test.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_the_healthcheck_fails_when_no_container_comes_up(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def no_containers(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text == f"{COMPOSE_CMD} ps -q":
            fake.calls.append(text)
            return ""
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", no_containers)
    monkeypatch.setattr(projects_module, "time", FakeClock())
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is False
    assert any("no active containers" in line.lower() for line in logs)


def test_the_healthcheck_gives_up_at_the_timeout(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container stuck on `starting` forever must end the loop, not hang the request."""
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__

    def forever_starting(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker inspect "):
            fake.calls.append(text)
            return json.dumps(
                [{"State": {"Status": "running", "Health": {"Status": "starting"}}}] * 2
            )
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", forever_starting)
    monkeypatch.setattr(projects_module, "time", FakeClock())
    with session_scope() as db:
        success, logs = update_single_project_logic("myapp", db, locale="en")

    assert success is False
    assert any("timeout" in line.lower() for line in logs)


def test_a_transient_docker_inspect_failure_does_not_trigger_a_rollback(
    stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The IDs come from a `ps -q` up to two seconds old, so a container recreated in
    between makes `docker inspect` exit non-zero. That used to reach the rollback and
    undo a deploy over a race."""
    fake = FakeDocker(images={"nginx:latest": OLD_NGINX, "redis:7": OLD_REDIS})
    original = fake.__call__
    failures = {"left": 1}

    def flaky_inspect(cmd, *args, **kwargs):
        text = cmd if isinstance(cmd, str) else " ".join(cmd)
        if text.startswith("docker inspect ") and failures["left"]:
            failures["left"] -= 1
            fake.calls.append(text)
            raise RuntimeError("No such object")
        return original(cmd, *args, **kwargs)

    monkeypatch.setattr(projects_module, "run_command", flaky_inspect)
    with session_scope() as db:
        success, _ = update_single_project_logic("myapp", db, locale="en")

    assert success is True
    assert len(fake.ran(UP_CMD)) == 1, "no rollback redeploy should have happened"
