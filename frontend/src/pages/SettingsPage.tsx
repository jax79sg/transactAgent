import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { addCategory, listCategories, removeCategory, renameCategory } from "../api/categories";
import { ApiError } from "../api/client";
import { getDriveAuthorizationUrl, getDriveStatus } from "../api/driveConnect";
import { getRestartGuidance, listSettingHistory, listSettings, updateSetting } from "../api/settings";
import type { CategoryDTO, RestartTargetDTO, SettingDTO } from "../api/types";

function DriveConnectionCard() {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { data: status } = useQuery({ queryKey: ["drive", "status"], queryFn: getDriveStatus });

  useEffect(() => {
    if (searchParams.get("driveConnected") === "true") {
      queryClient.invalidateQueries({ queryKey: ["drive", "status"] });
    }
  }, [searchParams, queryClient]);

  async function handleConnect() {
    const { authorizationUrl } = await getDriveAuthorizationUrl();
    window.location.href = authorizationUrl;
  }

  return (
    <div className="rounded border border-slate-200 p-4">
      <h2 className="mb-2 font-medium">Google Drive</h2>
      <p className="mb-3 text-sm text-slate-600">
        {status?.connected ? "Connected" : "Not connected"}
      </p>
      {/* Always shown, not just when disconnected: the only way to re-grant consent
          after a scope change (e.g. Epic 7 needing write access, not just read) is to
          run the connect flow again -- a "Connected" row from an old, narrower-scope
          grant otherwise leaves no way back into the flow at all. Caught live: a
          previously-connected credential silently kept returning 403s for the new
          write calls with no UI path to fix it (see aidlc-docs/audit.md 2026-08-08). */}
      <button data-testid="connect-drive-button" className="rounded bg-slate-900 px-4 py-2 text-white" onClick={handleConnect}>
        {status?.connected ? "Reconnect Google Drive" : "Connect Google Drive"}
      </button>
    </div>
  );
}

function CategoryRow({ category }: { category: CategoryDTO }) {
  const queryClient = useQueryClient();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(category.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [blockedCount, setBlockedCount] = useState<number | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["categories"] });

  const renameMutation = useMutation({
    mutationFn: () => renameCategory(category.id, name),
    onSuccess: () => {
      setRenaming(false);
      invalidate();
    },
  });

  const removeMutation = useMutation({
    mutationFn: () => removeCategory(category.id),
    onSuccess: () => {
      setConfirmingDelete(false);
      invalidate();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        setBlockedCount((err.body.details?.blockedByTransactionCount as number) ?? 0);
      }
    },
  });

  return (
    <li className="flex items-center gap-3 border-b border-slate-100 py-2">
      {renaming ? (
        <input
          className="rounded border px-2 py-1"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => renameMutation.mutate()}
          autoFocus
        />
      ) : (
        <span className={category.active ? "" : "text-slate-400 line-through"}>{category.name}</span>
      )}
      {!category.active && <span className="text-xs text-slate-400">(inactive)</span>}
      {category.isReserved && <span className="text-xs text-slate-400">(reserved)</span>}
      {!category.isReserved && (
        <div className="ml-auto flex gap-2 text-sm">
          <button onClick={() => setRenaming(true)} className="text-slate-500 hover:text-slate-800">
            Rename
          </button>
          <Dialog.Root open={confirmingDelete} onOpenChange={setConfirmingDelete}>
            <Dialog.Trigger asChild>
              <button className="text-red-500 hover:text-red-700">Remove</button>
            </Dialog.Trigger>
            <Dialog.Portal>
              <Dialog.Overlay className="fixed inset-0 bg-black/30" />
              <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded bg-white p-4 shadow-lg">
                <Dialog.Title>Remove "{category.name}"?</Dialog.Title>
                {blockedCount !== null && (
                  <p className="mt-2 text-sm text-red-600">
                    Cannot remove: {blockedCount} transactions still use this category.
                  </p>
                )}
                <div className="mt-4 flex justify-end gap-2">
                  <button onClick={() => setConfirmingDelete(false)}>Cancel</button>
                  <button
                    className="rounded bg-red-600 px-3 py-1 text-white"
                    onClick={() => removeMutation.mutate()}
                  >
                    Remove
                  </button>
                </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        </div>
      )}
    </li>
  );
}

function CategoryManagement() {
  const queryClient = useQueryClient();
  const { data: categories } = useQuery({ queryKey: ["categories"], queryFn: listCategories });
  const [newName, setNewName] = useState("");

  const addMutation = useMutation({
    mutationFn: () => addCategory(newName),
    onSuccess: () => {
      setNewName("");
      queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
  });

  return (
    <div className="rounded border border-slate-200 p-4">
      <h2 className="mb-2 font-medium">Categories</h2>
      <ul className="max-h-80 overflow-y-auto pr-1">{categories?.map((c) => <CategoryRow key={c.id} category={c} />)}</ul>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (newName.trim()) addMutation.mutate();
        }}
      >
        <input
          data-testid="new-category-input"
          className="rounded border px-2 py-1 text-sm"
          placeholder="New category name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button type="submit" className="rounded bg-slate-900 px-3 py-1 text-sm text-white">
          Add
        </button>
      </form>
    </div>
  );
}

// Configurable Application Settings: display order for the category groups the API
// returns per-setting (SettingDTO.category) -- matches .env.example's own section
// ordering (Matching -> Embedding -> Recurring Payments -> Backup -> Ingestion ->
// API & Access -> Ask AI) so the grouping here reads the same way .env.example does,
// per user feedback that .env's own organization should be properly referenced.
const CATEGORY_ORDER = [
  "Matching & Categorization",
  "Embedding & Semantic Matching",
  "Recurring Payments",
  "Backup",
  "Ingestion",
  "API & Access",
  "Ask AI",
];

// Deliberately looser than IngestionPage's 3s active-run poll, but tighter than
// NavBar's 30s ambient badge poll -- the user just saved a setting and is actively
// waiting to know when it's safe to restart, but a few seconds' staleness on "is the
// worker still busy" is harmless (business-logic-model.md).
const RESTART_GUIDANCE_POLL_INTERVAL_MS = 5000;

function formatSettingType(setting: SettingDTO): string {
  if (setting.type === "enum") return `one of: ${(setting.allowedValues ?? []).join(", ")}`;
  if (setting.min !== undefined && setting.max !== undefined) return `${setting.type}, ${setting.min}–${setting.max}`;
  if (setting.min !== undefined) return `${setting.type}, ≥ ${setting.min}`;
  return setting.type;
}

function RestartTargetLine({ settingName, target: initialTarget }: { settingName: string; target: RestartTargetDTO }) {
  const stillBusy = initialTarget.workerBusy === true;
  const { data: liveTargets } = useQuery({
    queryKey: ["settings", "restartGuidance", settingName],
    queryFn: () => getRestartGuidance(settingName),
    enabled: stillBusy,
    refetchInterval: (query) => {
      const current = query.state.data?.find((t) => t.owningService === initialTarget.owningService);
      return current?.workerBusy ? RESTART_GUIDANCE_POLL_INTERVAL_MS : false;
    },
  });

  const target = liveTargets?.find((t) => t.owningService === initialTarget.owningService) ?? initialTarget;

  if (target.workerBusy === true) {
    return (
      <li className="text-amber-700">
        {target.owningService}: worker is currently processing — wait for it to finish before restarting.
      </li>
    );
  }

  return (
    <li>
      {target.owningService}: <code data-testid="restart-command" className="rounded bg-slate-100 px-1 py-0.5">{target.restartCommand}</code>
    </li>
  );
}

function RestartGuidanceList({ settingName, targets }: { settingName: string; targets: RestartTargetDTO[] }) {
  return (
    <ul className="mt-2 space-y-1 text-sm" data-testid="restart-guidance">
      {targets.map((target) => (
        <RestartTargetLine key={target.owningService} settingName={settingName} target={target} />
      ))}
    </ul>
  );
}

function SettingConfirmDialog({
  setting,
  newValue,
  open,
  onOpenChange,
  onConfirm,
  pending,
}: {
  setting: SettingDTO;
  newValue: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  pending: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded bg-white p-4 shadow-lg">
          <Dialog.Title>Change "{setting.name}"?</Dialog.Title>
          <p className="mt-2 text-sm">
            From <code>{setting.value}</code> to <code>{newValue}</code>.
          </p>
          <p className="mt-2 text-sm text-slate-600">
            {setting.owningServices.join(" and ")} will need restarting to pick up this change.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button onClick={() => onOpenChange(false)}>Cancel</button>
            <button
              className="rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50"
              onClick={onConfirm}
              disabled={pending}
              data-testid="confirm-setting-change"
            >
              Confirm
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function SettingRow({ setting }: { setting: SettingDTO }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draftValue, setDraftValue] = useState(setting.value);
  const [confirming, setConfirming] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [result, setResult] = useState<{ setting: SettingDTO; restartGuidance: RestartTargetDTO[] } | null>(null);

  const mutation = useMutation({
    mutationFn: () => updateSetting(setting.name, draftValue),
    onSuccess: (data) => {
      setConfirming(false);
      setEditing(false);
      setValidationError(null);
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["settings", "list"] });
    },
    onError: (err) => {
      setConfirming(false);
      if (err instanceof ApiError && err.body.error === "invalid_setting_value") {
        setValidationError(err.body.message);
      } else {
        setValidationError("Something went wrong saving this setting.");
      }
    },
  });

  return (
    <li className="border-b border-slate-100 py-2" data-testid={`setting-row-${setting.name}`}>
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <span className="font-mono text-sm">{setting.name}</span>
          {setting.isOverridden && <span className="ml-2 text-xs text-slate-400">(customized)</span>}
          {/* Sourced from the API's own SettingDTO.description (catalog.py), which
              mirrors .env.example's per-setting explanatory comments -- not
              hardcoded here, so it can never drift from the real reasoning. */}
          <p className={`mt-1 text-xs ${setting.classification === "advanced" ? "text-amber-700" : "text-slate-500"}`}>
            {setting.description}
          </p>
        </div>
        {!editing && (
          <>
            <span className="text-sm text-slate-600">{setting.value}</span>
            <button onClick={() => setEditing(true)} className="text-slate-500 hover:text-slate-800">
              Edit
            </button>
          </>
        )}
      </div>
      {editing && (
        <form
          className="mt-2 flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setConfirming(true);
          }}
        >
          <input
            className="rounded border px-2 py-1 text-sm"
            value={draftValue}
            onChange={(e) => setDraftValue(e.target.value)}
            data-testid={`setting-input-${setting.name}`}
          />
          <span className="text-xs text-slate-400">{formatSettingType(setting)}</span>
          <button type="submit" className="rounded bg-slate-900 px-2 py-1 text-xs text-white">
            Save
          </button>
          <button type="button" onClick={() => setEditing(false)} className="text-xs text-slate-500">
            Cancel
          </button>
        </form>
      )}
      {validationError && <p className="mt-1 text-sm text-red-600">{validationError}</p>}
      {result && (
        <div className="mt-2 rounded bg-slate-50 p-2">
          <p className="text-sm">Saved.</p>
          <RestartGuidanceList settingName={setting.name} targets={result.restartGuidance} />
        </div>
      )}
      <SettingConfirmDialog
        setting={setting}
        newValue={draftValue}
        open={confirming}
        onOpenChange={setConfirming}
        onConfirm={() => mutation.mutate()}
        pending={mutation.isPending}
      />
    </li>
  );
}

function SettingHistoryList() {
  const [expanded, setExpanded] = useState(false);
  const { data: history } = useQuery({
    queryKey: ["settings", "history"],
    queryFn: listSettingHistory,
    enabled: expanded,
  });

  return (
    <div className="rounded border border-slate-200 p-4">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="font-medium"
        data-testid="toggle-setting-history"
      >
        Change History {expanded ? "▾" : "▸"}
      </button>
      {expanded && (
        <ul className="mt-3 max-h-60 space-y-1 overflow-y-auto text-sm">
          {history?.length === 0 && <li className="text-slate-400">No changes yet.</li>}
          {history?.map((entry) => (
            <li key={entry.id}>
              <span className="font-mono">{entry.settingName}</span>: {entry.previousValue ?? "(default)"} →{" "}
              {entry.newValue} <span className="text-xs text-slate-400">({entry.changedAt})</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ApplicationSettingsSection() {
  const { data: settings } = useQuery({ queryKey: ["settings", "list"], queryFn: listSettings });

  // Grouped by SettingDTO.category (server-side, matching .env.example's own
  // section organization), in CATEGORY_ORDER -- any category not in that list
  // (shouldn't happen, but doesn't crash if catalog.py adds one later) is appended
  // at the end rather than silently dropped.
  const byCategory = new Map<string, SettingDTO[]>();
  for (const setting of settings ?? []) {
    const list = byCategory.get(setting.category) ?? [];
    list.push(setting);
    byCategory.set(setting.category, list);
  }
  const orderedCategories = [
    ...CATEGORY_ORDER.filter((c) => byCategory.has(c)),
    ...[...byCategory.keys()].filter((c) => !CATEGORY_ORDER.includes(c)),
  ];

  return (
    <div className="space-y-4">
      <h2 className="font-medium">Application Settings</h2>
      {orderedCategories.map((category) => {
        const items = byCategory.get(category) ?? [];
        const hasAdvanced = items.some((s) => s.classification === "advanced");
        return (
          <div
            key={category}
            className={`rounded border p-4 ${hasAdvanced ? "border-amber-300 bg-amber-50" : "border-slate-200"}`}
            data-testid={`setting-category-${category}`}
          >
            <h3 className="mb-2 text-sm font-semibold">{category}</h3>
            <ul>
              {items.map((setting) => (
                <SettingRow key={setting.name} setting={setting} />
              ))}
            </ul>
          </div>
        );
      })}
      <SettingHistoryList />
    </div>
  );
}

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      {/* Drive connection first: the category list can run to 40+ rows, and previously
          being listed above Drive forced scrolling past all of them just to reach it. */}
      <DriveConnectionCard />
      <CategoryManagement />
      <ApplicationSettingsSection />
    </div>
  );
}
