import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { addCategory, listCategories, removeCategory, renameCategory } from "../api/categories";
import { ApiError } from "../api/client";
import { getDriveAuthorizationUrl, getDriveStatus } from "../api/driveConnect";
import type { CategoryDTO } from "../api/types";

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

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      {/* Drive connection first: the category list can run to 40+ rows, and previously
          being listed above Drive forced scrolling past all of them just to reach it. */}
      <DriveConnectionCard />
      <CategoryManagement />
    </div>
  );
}
