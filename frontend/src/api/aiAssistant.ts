import { apiRequest } from "./client";
import type { AskAiRequest, AskAiResponse } from "./types";

export function askAi(request: AskAiRequest): Promise<AskAiResponse> {
  return apiRequest<AskAiResponse>("/ai/ask", { method: "POST", body: request });
}
