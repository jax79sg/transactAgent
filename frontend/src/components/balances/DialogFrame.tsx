import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

// Epic 13: the app's modal (Radix Dialog, as RemovalConfirmDialog uses it: focus is trapped and restored on close),
// shared by the four account dialogs so they look and behave alike. The description is required: Radix wants one for
// the dialog's accessible description.
export function DialogFrame({
  testId,
  title,
  description,
  onClose,
  children,
  footer,
}: {
  testId: string;
  title: string;
  description: ReactNode;
  onClose: () => void;
  children?: ReactNode;
  footer: ReactNode;
}) {
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/30" />
        <Dialog.Content
          data-testid={testId}
          className="fixed left-1/2 top-1/2 max-h-[90vh] w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded bg-white p-4 shadow-lg dark:bg-slate-800 dark:text-slate-100"
        >
          <Dialog.Title className="font-medium">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-slate-600 dark:text-slate-300">{description}</Dialog.Description>
          {children && <div className="mt-3">{children}</div>}
          <div className="mt-4 flex flex-wrap justify-end gap-3">{footer}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export const FIELD_CLASS =
  "w-full rounded border border-slate-300 px-2 py-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100";
export const CANCEL_CLASS = "min-h-[40px] px-3 py-1 text-slate-600 dark:text-slate-300";
export const PRIMARY_CLASS =
  "min-h-[40px] rounded bg-slate-900 px-3 py-1 text-white disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900";
export const DANGER_CLASS = "min-h-[40px] rounded bg-red-700 px-3 py-1 text-white disabled:opacity-50 dark:bg-red-600";
export const ERROR_CLASS = "mt-2 text-sm text-red-600 dark:text-red-400";
