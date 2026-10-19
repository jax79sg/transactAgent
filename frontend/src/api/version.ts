import { apiRequest } from "./client";

export interface ServerVersion {
  version: string;
}

/** The release the server is on (unauthenticated, so it works on the login page too). */
export function getServerVersion(): Promise<ServerVersion> {
  return apiRequest<ServerVersion>("/version");
}
