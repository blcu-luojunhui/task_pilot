import { apiClient, unwrap } from './client';
import { hashPassword } from '@/utils/crypto';

export interface AccountInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  daily_token_limit: number;
  today_tokens_used: number;
  created_at: string;
  updated_at: string;
}

export interface AdminUserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  daily_token_limit: number;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListData {
  total: number;
  page: number;
  page_size: number;
  items: AdminUserInfo[];
}

export interface RegisterResult {
  account_id: number;
  username: string;
  email: string;
  token: string;
  token_prefix: string;
  expires_at: string | null;
}

export interface LoginResult {
  account_id: number;
  username: string;
  token: string;
  token_prefix: string;
  expires_at: string | null;
}

export interface TokenInfo {
  id: number;
  token_prefix: string;
  name: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface CreateTokenResult {
  token: string;
  token_prefix: string;
  name: string | null;
  expires_at: string | null;
}

export async function register(username: string, email: string, password: string) {
  const hashed = await hashPassword(password);
  return unwrap<RegisterResult>(
    apiClient.post('/auth/register', { username, email, password: hashed }),
  );
}

export async function login(username: string, password: string) {
  const hashed = await hashPassword(password);
  return unwrap<LoginResult>(
    apiClient.post('/auth/login', { username, password: hashed }),
  );
}

export async function logout() {
  return unwrap<null>(apiClient.post('/auth/logout'));
}

export async function getMe() {
  return unwrap<AccountInfo>(apiClient.get('/auth/me'));
}

export async function createToken(name?: string) {
  return unwrap<CreateTokenResult>(
    apiClient.post('/auth/tokens', name ? { name } : {}),
  );
}

export async function listTokens() {
  return unwrap<TokenInfo[]>(apiClient.get('/auth/tokens'));
}

export async function revokeToken(tokenId: number) {
  return unwrap<null>(apiClient.delete(`/auth/tokens/${tokenId}`));
}

export async function listUsers(page = 1, pageSize = 20) {
  return unwrap<AdminUserListData>(
    apiClient.get('/auth/admin/users', { params: { page, page_size: pageSize } }),
  );
}

export async function updateUserRole(userId: number, role: string) {
  return unwrap<null>(
    apiClient.put(`/auth/admin/users/${userId}/role`, { role }),
  );
}

export async function updateUserQuota(userId: number, dailyTokenLimit: number) {
  return unwrap<null>(
    apiClient.put(`/auth/admin/users/${userId}/quota`, { daily_token_limit: dailyTokenLimit }),
  );
}
