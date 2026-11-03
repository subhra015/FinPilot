/**
 * Authentication API Service (Layer 12 & Layer 13).
 */

import { api } from "./client";
import type { AuthResponse, UserProfile, UserRole } from "./types";

export interface RegisterPayload {
  email: string;
  password: string;
  role?: UserRole;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface MFALoginPayload {
  user_id: string;
  totp_code: string;
}

export const authApi = {
  register: (payload: RegisterPayload): Promise<UserProfile> =>
    api.post<UserProfile>("/api/auth/register", payload),

  login: (payload: LoginPayload): Promise<AuthResponse> =>
    api.post<AuthResponse>("/api/auth/login", payload),

  verifyMfaLogin: (payload: MFALoginPayload): Promise<AuthResponse> =>
    api.post<AuthResponse>("/api/auth/mfa/verify-login", payload),

  getCurrentUser: (): Promise<UserProfile> =>
    api.get<UserProfile>("/api/auth/me"),

  logout: (): Promise<{ message: string }> =>
    api.post<{ message: string }>("/api/auth/logout"),

  setupMfa: (): Promise<{ secret: string; otpauth_uri: string }> =>
    api.post<{ secret: string; otpauth_uri: string }>("/api/auth/mfa/setup"),

  verifyMfaSetup: (totp_code: string): Promise<{ message: string }> =>
    api.post<{ message: string }>("/api/auth/mfa/verify", { totp_code }),
};
