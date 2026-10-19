import { describe, expect, test } from "bun:test";
import { signupFormError, toSessionState, toSessionUser } from "./auth";

const user = { user_id: "usr_00000000000000aa", username: "alice", display_name: "Alice", is_admin: false, created_at: "2026-10-19T10:00:00" };

describe("toSessionUser", () => {
  test("signed out maps to null", () => {
    expect(toSessionUser({ authenticated: false, user: null, bee_link: null })).toBeNull();
  });

  test("linked Bee account is exposed as connected", () => {
    const s = toSessionUser({ authenticated: true, user, bee_link: { user_id: user.user_id, state: "linked", bee_first_name: "Ada" } });
    expect(s?.handle).toBe("Alice");
    expect(s?.bee_connected).toBe(true);
    expect(s?.bee_account).toBe("Ada");
  });

  test("pairing is not connected and hides the account name", () => {
    const s = toSessionUser({ authenticated: true, user, bee_link: { user_id: user.user_id, state: "pairing", bee_first_name: "Ada" } });
    expect(s?.bee_connected).toBe(false);
    expect(s?.bee_account).toBeNull();
  });
});

describe("toSessionState", () => {
  test("signed out exposes whether registration is open", () => {
    expect(toSessionState({ authenticated: false, user: null, bee_link: null, signup_enabled: true })).toEqual({
      user: null,
      signupEnabled: true,
    });
    expect(toSessionState({ authenticated: false, user: null, bee_link: null }).signupEnabled).toBe(false);
  });
});

describe("signupFormError", () => {
  test("accepts a valid form", () => {
    expect(signupFormError("dave", "correct horse battery", "correct horse battery")).toBeNull();
  });

  test("rejects invalid usernames, short and mismatched passwords", () => {
    expect(signupFormError("d", "correct horse battery", "correct horse battery")).toContain("Username");
    expect(signupFormError("dave smith", "correct horse battery", "correct horse battery")).toContain("Username");
    expect(signupFormError("dave", "short", "short")).toContain("12 characters");
    expect(signupFormError("dave", "correct horse battery", "correct horse batterY")).toBe("Passwords do not match");
  });
});
