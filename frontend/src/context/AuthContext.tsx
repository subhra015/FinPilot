/**
 * Authentication Context & State Management (SEC-01, SEC-09, SEC-15).
 *
 * Governed by:
 * - SECURITY_CHECKLIST.md SEC-02: Zero tokens/credentials in localStorage.
 * - SECURITY_CHECKLIST.md SEC-09: Role-based view helpers (server remains authoritative).
 * - SECURITY_CHECKLIST.md SEC-15: Opaque server-side session cookies.
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { authApi } from "../api/auth";
import { setUnauthorizedHandler } from "../api/client";
import type { UserProfile, UserRole } from "../api/types";

interface AuthContextType {
  user: UserProfile | null;
  role: UserRole;
  isAuthenticated: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  sessionExpired: boolean;
  dismissSessionExpired: () => void;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; userId?: string }>;
  verifyMfa: (userId: string, code: string) => Promise<void>;
  register: (email: string, password: string, role?: UserRole) => Promise<UserProfile>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [sessionExpired, setSessionExpired] = useState<boolean>(false);

  const refreshUser = useCallback(async () => {
    try {
      const profile = await authApi.getCurrentUser();
      setUser(profile);
      setSessionExpired(false);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Register global 401 unauthorized handler
    setUnauthorizedHandler(() => {
      setUser(null);
      setSessionExpired(true);
    });

    // Initial session probe
    void refreshUser();

    return () => {
      setUnauthorizedHandler(null);
    };
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    if (res.mfa_required) {
      return { mfaRequired: true, userId: res.user?.user_id || res.user_id };
    }
    if (res.user) {
      setUser(res.user);
      setSessionExpired(false);
    }
    return { mfaRequired: false };
  };

  const verifyMfa = async (userId: string, code: string) => {
    const res = await authApi.verifyMfaLogin({ user_id: userId, totp_code: code });
    if (res.user) {
      setUser(res.user);
      setSessionExpired(false);
    }
  };

  const register = async (email: string, password: string, role: UserRole = "USER") => {
    const newUser = await authApi.register({ email, password, role });
    return newUser;
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      setSessionExpired(false);
    }
  };

  const dismissSessionExpired = () => {
    setSessionExpired(false);
  };

  const role: UserRole = user?.role || "USER";
  const isAuthenticated = !!user;
  const isAdmin = role === "ADMIN";

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        isAuthenticated,
        isAdmin,
        isLoading,
        sessionExpired,
        dismissSessionExpired,
        login,
        verifyMfa,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
