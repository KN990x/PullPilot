from __future__ import annotations

from typing import Any

_FALLBACK = "es"

_MESSAGES: dict[str, dict[str, str]] = {
    "es": {
        "log.prefix_ok": "[OK]",
        "log.prefix_err": "[ERR]",
        "log.prefix_warn": "[WARN]",
        "log.prefix_info": "[INFO]",
        "log.status_ok": "OK",
        "log.status_error": "ERROR",
        "update.header": "=== ACTUALIZANDO: {name} ===",
        "update.git_snapshot": "Snapshot creado. Commit actual: {commit}",
        "update.git_snapshot_warn": "No se pudo guardar estado Git: {exc}",
        "update.git_pull": "Ejecutando git pull...",
        "update.compose_pull": "Descargando imagenes nuevas...",
        "update.full_stop_down": "Modo Full Stop: bajando servicios...",
        "update.compose_stop": "Deteniendo contenedores...",
        "update.compose_up": "Recreando contenedores...",
        "update.health_wait": "Verificando salud (timeout: {timeout}s)...",
        "update.health_passed": "Healthcheck superado: todos los servicios estables.",
        "update.completed_banner": "=== PROCESO COMPLETADO CORRECTAMENTE ===",
        "update.critical_failure": "FALLO CRITICO DETECTADO: {exc}",
        "update.rollback_start": "INICIANDO ROLLBACK AUTOMATICO...",
        "update.rollback_git_reset": "Codigo revertido a commit {commit}.",
        "update.rollback_redeploy": "Forzando redespliegue de version anterior...",
        "update.rollback_success": "Rollback exitoso. El sistema ha vuelto al estado previo.",
        "update.rollback_note": "NOTA: Se ha realizado un rollback automatico para restaurar el servicio.",
        "update.rollback_fatal": "FATAL: El rollback tambien fallo: {exc}",
        "update.rollback_impossible": "No es posible hacer rollback (no es un repo Git o no se guardo el estado).",
        "error.error_prefix": "ERROR:",
        "error.db_project_not_found": "Proyecto no encontrado en la base de datos.",
        "error.invalid_compose_stack": "El directorio del proyecto no es un stack compose valido.",
        "error.path_resolve_failed": "No se pudo resolver la ruta del proyecto: {exc}",
        "error.path_outside_root": "La ruta del proyecto no esta bajo STACKS_PATH (posible dato alterado en BD).",
        "health.timeout": "Timeout: Los servicios no iniciaron correctamente en {timeout}s.",
        "health.no_containers": "No se detectaron contenedores activos tras el despliegue.",
        "health.restarting": "Contenedor {cid} detectado en bucle de reinicio.",
        "health.exited": "Contenedor {cid} finalizo con error (code: {code}).",
        "health.unhealthy": "Healthcheck fallido para {cid} (unhealthy).",
        "docker.timeout_command": "Timeout del comando: {cmd}",
        "docker.timeout_configured": "Timeout configurado: {seconds}s",
        "docker.error_command": "Error en comando: {cmd}",
        "docker.stderr_label": "Stderr:",
        "http.history_save_failed": "Error al guardar el historial",
        "http.update_failed": "La actualizacion fallo. Consulta el historial en la UI o los logs del servidor.",
        "http.project_not_found": "Proyecto no encontrado",
        "http.project_save_failed": "Error al guardar el proyecto",
        "http.update_in_progress": "Ese proyecto ya se esta actualizando. Espera a que termine.",
        "http.schedule_not_found": "Programacion no encontrada",
        "http.schedule_save_failed": "Error al guardar la programacion",
        "http.schedule_delete_failed": "Error al eliminar la programacion",
        "api.update_all_started": "Actualizacion global iniciada en segundo plano",
        "summary.project": "{name}: {status}",
        "scheduler.global_summary": "Actualizacion global: {ok} OK, {errors} errores",
        "scheduler.scheduled_ok": "[Programada] {target}: OK",
        "scheduler.scheduled_error": "[Programada] {target}: ERROR",
        "scheduler.scheduled_exception": "[Programada] {target}: EXCEPCION",
        "scheduler.safe_cleanup_done": "Limpieza de imagenes obsoletas completada (modo seguro).",
        "scheduler.docker_output": "Salida Docker:",
        "scheduler.safe_cleanup_failed": "Error en limpieza de imagenes: {exc}",
        "scheduler.cleanup_skipped": "[WARN] LIMPIEZA OMITIDA: Se detectaron {errors} errores durante la actualizacion. No se ejecutara prune para facilitar la depuracion.",
        "scheduler.internal_loop_error": "[ERR] Error interno en el bucle principal: {exc}",
        "scheduler.project_busy": "[WARN] {name} omitido: ya habia una actualizacion en curso.",
        "scheduler.status_pruning": "Limpiando sistema (prune seguro)...",
    },
    "en": {
        "log.prefix_ok": "[OK]",
        "log.prefix_err": "[ERR]",
        "log.prefix_warn": "[WARN]",
        "log.prefix_info": "[INFO]",
        "log.status_ok": "OK",
        "log.status_error": "ERROR",
        "update.header": "=== UPDATING: {name} ===",
        "update.git_snapshot": "Snapshot created. Current commit: {commit}",
        "update.git_snapshot_warn": "Could not save Git state: {exc}",
        "update.git_pull": "Running git pull...",
        "update.compose_pull": "Pulling new images...",
        "update.full_stop_down": "Full Stop mode: bringing services down...",
        "update.compose_stop": "Stopping containers...",
        "update.compose_up": "Recreating containers...",
        "update.health_wait": "Checking health (timeout: {timeout}s)...",
        "update.health_passed": "Healthcheck passed: all services stable.",
        "update.completed_banner": "=== PROCESS COMPLETED SUCCESSFULLY ===",
        "update.critical_failure": "CRITICAL FAILURE DETECTED: {exc}",
        "update.rollback_start": "STARTING AUTOMATIC ROLLBACK...",
        "update.rollback_git_reset": "Code reverted to commit {commit}.",
        "update.rollback_redeploy": "Forcing redeploy of previous version...",
        "update.rollback_success": "Rollback successful. The system has been restored to the previous state.",
        "update.rollback_note": "NOTE: An automatic rollback was performed to restore the service.",
        "update.rollback_fatal": "FATAL: Rollback also failed: {exc}",
        "update.rollback_impossible": "Rollback not possible (not a Git repo or state was not saved).",
        "error.error_prefix": "ERROR:",
        "error.db_project_not_found": "Project not found in the database.",
        "error.invalid_compose_stack": "The project directory is not a valid Compose stack.",
        "error.path_resolve_failed": "Could not resolve project path: {exc}",
        "error.path_outside_root": "Project path is not under STACKS_PATH (possible tampered DB data).",
        "health.timeout": "Timeout: Services did not become healthy within {timeout}s.",
        "health.no_containers": "No active containers detected after deploy.",
        "health.restarting": "Container {cid} stuck in a restart loop.",
        "health.exited": "Container {cid} exited with error (code: {code}).",
        "health.unhealthy": "Healthcheck failed for {cid} (unhealthy).",
        "docker.timeout_command": "Command timeout: {cmd}",
        "docker.timeout_configured": "Configured timeout: {seconds}s",
        "docker.error_command": "Command error: {cmd}",
        "docker.stderr_label": "Stderr:",
        "http.history_save_failed": "Failed to save history",
        "http.update_failed": "Update failed. Check history in the UI or server logs.",
        "http.project_not_found": "Project not found",
        "http.project_save_failed": "Failed to save project",
        "http.update_in_progress": "That project is already being updated. Wait for it to finish.",
        "http.schedule_not_found": "Schedule not found",
        "http.schedule_save_failed": "Failed to save schedule",
        "http.schedule_delete_failed": "Failed to delete schedule",
        "api.update_all_started": "Global update started in the background",
        "summary.project": "{name}: {status}",
        "scheduler.global_summary": "Global update: {ok} OK, {errors} errors",
        "scheduler.scheduled_ok": "[Scheduled] {target}: OK",
        "scheduler.scheduled_error": "[Scheduled] {target}: ERROR",
        "scheduler.scheduled_exception": "[Scheduled] {target}: EXCEPTION",
        "scheduler.safe_cleanup_done": "Obsolete image cleanup completed (safe mode).",
        "scheduler.docker_output": "Docker output:",
        "scheduler.safe_cleanup_failed": "Image cleanup error: {exc}",
        "scheduler.cleanup_skipped": "[WARN] CLEANUP SKIPPED: {errors} error(s) during update. Prune will not run to aid debugging.",
        "scheduler.internal_loop_error": "[ERR] Internal error in main loop: {exc}",
        "scheduler.project_busy": "[WARN] {name} skipped: an update was already running.",
        "scheduler.status_pruning": "Cleaning up system (safe prune)...",
    },
}


def normalize_locale(raw: str | None) -> str:
    if not raw:
        return _FALLBACK
    base = raw.split("-")[0].lower().strip()
    if base in _MESSAGES:
        return base
    return _FALLBACK


def t(key: str, locale: str, **kwargs: Any) -> str:
    loc = normalize_locale(locale)
    table = _MESSAGES.get(loc) or _MESSAGES[_FALLBACK]
    template = table.get(key)
    if template is None:
        template = _MESSAGES[_FALLBACK].get(key, key)
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
