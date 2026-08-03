# Logical Components — Unit 3: Ingestion Worker Service

## Component: Worker Loop
- **Type**: `asyncio` polling loop, the process entrypoint
- **Role**: Polls for queued `IngestionRun`/`RecategorizationJob` rows every 5s, dispatches to the Orchestrator logic

## Component: GeminiClient
- **Type**: Thin wrapper around `google-genai`
- **Role**: Sends PDF page images + extraction prompt, returns raw structured response; retry-with-backoff applied here (NFR Design pattern above)

## Component: OpenRouterClient
- **Type**: Thin wrapper around `openai` client configured with OpenRouter's `base_url`
- **Role**: Sends categorization prompt (description + whitelist), returns the model's answer; same retry-with-backoff pattern

## Component: DriveClient
- **Type**: Thin wrapper around `google-api-python-client` + `google-auth`
- **Role**: Reads the refresh token from `oauth_credentials` (written by Unit 2's OAuth flow), refreshes the access token as needed, lists/downloads files from the configured folder

## Component: FxRateClient
- **Type**: Thin wrapper around `exchangerate.host`'s HTTP API
- **Role**: Fetches historical rates (fallback path only, per WR-6); results cached in `fx_rate_cache`

## No Additional Infrastructure Components

No task queue, cache service, or circuit breaker — consistent with Application Design and Units 1/2's "keep it simple" decisions. The FX rate cache is a plain database table (Unit 1), not a separate caching infrastructure component.
