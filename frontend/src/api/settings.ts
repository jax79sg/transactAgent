import { apiRequest } from "./client";
import type { RestartTargetDTO, SettingChangeDTO, SettingChangeResultDTO, SettingDTO } from "./types";

export function listSettings(): Promise<SettingDTO[]> {
  return apiRequest<SettingDTO[]>("/settings");
}

export function getSetting(name: string): Promise<SettingDTO> {
  return apiRequest<SettingDTO>(`/settings/${name}`);
}

export function updateSetting(name: string, value: string): Promise<SettingChangeResultDTO> {
  return apiRequest<SettingChangeResultDTO>(`/settings/${name}`, { method: "PUT", body: { value } });
}

export function getRestartGuidance(name: string): Promise<RestartTargetDTO[]> {
  return apiRequest<RestartTargetDTO[]>(`/settings/${name}/restart-guidance`);
}

export function listSettingHistory(): Promise<SettingChangeDTO[]> {
  return apiRequest<SettingChangeDTO[]>("/settings/history");
}
