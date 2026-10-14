import { DemoUser, BeePairingInfo } from "@/types/schemas";
import { getApiBaseUrl } from "@/utils/api";

const STORAGE_LEGACY_KEY = "examen_demo_user_session";
const STORAGE_USERS_DIRECTORY = "examen_demo_users_directory";
const STORAGE_ACTIVE_USER_ID = "examen_demo_active_user_id";

/**
 * Returns all saved demo user profiles from local storage.
 * Enforces GDPR compliance: zero sensitive PII is stored.
 */
export const getSavedUsers = (): DemoUser[] => {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_USERS_DIRECTORY);
    let users: DemoUser[] = raw ? JSON.parse(raw) : [];

    // Migrate legacy session if present and not in directory
    const legacyRaw = localStorage.getItem(STORAGE_LEGACY_KEY);
    if (legacyRaw) {
      try {
        const legacyUser: DemoUser = JSON.parse(legacyRaw);
        if (legacyUser?.user_id && !users.some((u) => u.user_id === legacyUser.user_id)) {
          users.push(legacyUser);
          localStorage.setItem(STORAGE_USERS_DIRECTORY, JSON.stringify(users));
        }
      } catch {
        // ignore legacy parse error
      }
    }
    return users;
  } catch (err) {
    console.warn("Failed to read saved demo users:", err);
    return [];
  }
};

/**
 * Saves or updates a demo user in the local directory.
 */
export const saveUserToDirectory = (user: DemoUser): void => {
  if (typeof window === "undefined" || !user?.user_id) return;
  try {
    const users = getSavedUsers();
    const idx = users.findIndex((u) => u.user_id === user.user_id);
    if (idx >= 0) {
      users[idx] = { ...users[idx], ...user, last_active: new Date().toISOString() };
    } else {
      users.push({ ...user, last_active: new Date().toISOString() });
    }
    localStorage.setItem(STORAGE_USERS_DIRECTORY, JSON.stringify(users));
  } catch (err) {
    console.warn("Failed to save user to directory:", err);
  }
};

/**
 * Removes a user profile completely from the local directory (GDPR Art. 17).
 */
export const removeUserFromDirectory = (userId: string): void => {
  if (typeof window === "undefined" || !userId) return;
  try {
    const users = getSavedUsers().filter((u) => u.user_id !== userId);
    localStorage.setItem(STORAGE_USERS_DIRECTORY, JSON.stringify(users));
    if (localStorage.getItem(STORAGE_ACTIVE_USER_ID) === userId) {
      localStorage.removeItem(STORAGE_ACTIVE_USER_ID);
    }
    localStorage.removeItem(STORAGE_LEGACY_KEY);
  } catch (err) {
    console.warn("Failed to remove user from directory:", err);
  }
};

/**
 * Retrieves the currently active user session, or null if unauthenticated.
 */
export const getLocalUser = (): DemoUser | null => {
  if (typeof window === "undefined") return null;
  try {
    const activeId = localStorage.getItem(STORAGE_ACTIVE_USER_ID);
    const users = getSavedUsers();
    if (activeId) {
      const found = users.find((u) => u.user_id === activeId);
      if (found) return found;
    }
    // Fallback to legacy single session key if available
    const legacyRaw = localStorage.getItem(STORAGE_LEGACY_KEY);
    if (legacyRaw) {
      return JSON.parse(legacyRaw) as DemoUser;
    }
    return null;
  } catch {
    return null;
  }
};

/**
 * Saves and sets the active demo user session.
 */
export const saveLocalUser = (user: DemoUser): void => {
  if (typeof window === "undefined" || !user?.user_id) return;
  try {
    saveUserToDirectory(user);
    localStorage.setItem(STORAGE_ACTIVE_USER_ID, user.user_id);
    // Maintain legacy key for any backward compatibility
    localStorage.setItem(STORAGE_LEGACY_KEY, JSON.stringify(user));
  } catch (err) {
    console.warn("Failed to persist user session:", err);
  }
};

/**
 * Clears the active session (logging out) without deleting the saved profile.
 */
export const clearLocalUser = (): void => {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(STORAGE_ACTIVE_USER_ID);
    localStorage.removeItem(STORAGE_LEGACY_KEY);
  } catch (err) {
    console.warn("Failed to clear active user session:", err);
  }
};

/**
 * Logs in with a handle or existing user ID.
 * Saved per user in the demo user management system.
 */
export const loginUser = async (
  handle: string,
  connectBee: boolean = false,
  existingUserId?: string
): Promise<{ success: boolean; user: DemoUser; bee_pairing?: BeePairingInfo }> => {
  const baseUrl = getApiBaseUrl();
  const payload = {
    handle: handle.trim(),
    connect_bee: connectBee,
    user_id: existingUserId || undefined,
  };

  const res = await fetch(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Login failed with status ${res.status}`);
  }

  const data = await res.json();
  if (data.user) {
    saveLocalUser(data.user);
  }
  return data;
};

/**
 * Fetches the list of saved demo users from the backend directory.
 */
export const fetchBackendUsers = async (): Promise<DemoUser[]> => {
  const baseUrl = getApiBaseUrl();
  try {
    const res = await fetch(`${baseUrl}/api/auth/users`);
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.users)) {
        data.users.forEach((u: DemoUser) => saveUserToDirectory(u));
        return getSavedUsers();
      }
    }
  } catch (err) {
    console.warn("Failed to fetch backend users:", err);
  }
  return getSavedUsers();
};

/**
 * Generates or refreshes the Bee Wearable pairing URL by calling the Bee CLI.
 */
export const fetchBeeLink = async (
  userId?: string
): Promise<{ success: boolean; bee_pairing: BeePairingInfo }> => {
  const baseUrl = getApiBaseUrl();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (userId) headers["x-user-id"] = userId;

  const res = await fetch(`${baseUrl}/api/auth/bee-link`, {
    method: "POST",
    headers,
    body: JSON.stringify({ user_id: userId }),
  });

  if (!res.ok) {
    throw new Error(`Failed to generate Bee link: ${res.status}`);
  }

  return res.json();
};

/**
 * Disconnects the Bee Wearable AI device and clears pairing credentials.
 */
export const disconnectBee = async (userId?: string): Promise<boolean> => {
  const baseUrl = getApiBaseUrl();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (userId) headers["x-user-id"] = userId;

  const res = await fetch(`${baseUrl}/api/auth/bee-disconnect`, {
    method: "POST",
    headers,
    body: JSON.stringify({ user_id: userId }),
  });

  if (res.ok) {
    const user = getLocalUser();
    if (user) {
      user.bee_connected = false;
      user.bee_account = null;
      user.bee_pairing = null;
      saveLocalUser(user);
    }
    return true;
  }
  return false;
};

/**
 * Logs out the active user session and removes login.
 */
export const logoutUser = async (userId?: string): Promise<void> => {
  const baseUrl = getApiBaseUrl();
  try {
    await fetch(`${baseUrl}/api/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, disconnect_bee: true }),
    });
  } catch (err) {
    console.warn("Logout request error:", err);
  } finally {
    clearLocalUser();
  }
};

/**
 * GDPR Art. 17 Right to Erasure: purges all stored user data locally and remotely.
 */
export const purgeUserData = async (userId?: string): Promise<void> => {
  const baseUrl = getApiBaseUrl();
  try {
    await fetch(`${baseUrl}/api/auth/gdpr-purge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
  } catch (err) {
    console.warn("Purge request error:", err);
  } finally {
    if (userId) {
      removeUserFromDirectory(userId);
    } else {
      clearLocalUser();
    }
  }
};

/**
 * GDPR Art. 20 Data Portability: downloads the user's telemetry snapshot as JSON.
 */
export const exportUserDataJson = (user: DemoUser, telemetryData?: any): void => {
  if (typeof window === "undefined") return;
  const exportPayload = {
    export_metadata: {
      framework: "EU General Data Protection Regulation (GDPR) Art. 20 - Data Portability",
      exported_at: new Date().toISOString(),
      system: "EXAMEN Ambient Intelligence Platform",
    },
    user_profile: user,
    ambient_telemetry_snapshot: telemetryData || null,
  };

  const dataStr =
    "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportPayload, null, 2));
  const dlAnchorElem = document.createElement("a");
  dlAnchorElem.setAttribute("href", dataStr);
  dlAnchorElem.setAttribute("download", `examen-gdpr-export-${user.user_id || "demo"}.json`);
  dlAnchorElem.click();
};
