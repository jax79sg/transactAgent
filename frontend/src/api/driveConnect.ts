import { apiRequest } from "./client";
import type { DriveAuthorizationUrl, DriveConnectionStatus } from "./types";

export function getDriveStatus(): Promise<DriveConnectionStatus> {
  return apiRequest<DriveConnectionStatus>("/drive/status");
}

export function getDriveAuthorizationUrl(): Promise<DriveAuthorizationUrl> {
  return apiRequest<DriveAuthorizationUrl>("/drive/connect");
}
