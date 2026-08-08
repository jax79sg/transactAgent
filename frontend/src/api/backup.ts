import { apiRequest } from "./client";
import type { BackupStatusResponse } from "./types";

export function getBackupStatus(): Promise<BackupStatusResponse> {
  return apiRequest<BackupStatusResponse>("/backups/status");
}
