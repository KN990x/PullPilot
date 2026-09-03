/**
 * Username and password bounds, mirroring `server/auth_policy.py`.
 *
 * That file is the source of truth: the API rejects anything outside these, and what is
 * here only exists so the browser can say so before a round trip. They were spelled out
 * as literals in the two forms, three files away from the values they had to match.
 */
export const USERNAME_MIN_LEN = 3;
export const USERNAME_MAX_LEN = 64;
export const USERNAME_PATTERN = "^[A-Za-z0-9._@+-]+$";
export const PASSWORD_MIN_LEN = 8;
export const PASSWORD_MAX_LEN = 128;
