import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const SHEET_SIDES = {
  top: "top",
  right: "right",
  bottom: "bottom",
  left: "left",
} as const;

type SheetSide = (typeof SHEET_SIDES)[keyof typeof SHEET_SIDES];

interface SheetContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  dialogRef: React.RefObject<HTMLDialogElement | null>;
  side: SheetSide;
  setSide: (side: SheetSide) => void;
}

const SheetContext = React.createContext<SheetContextValue | null>(null);

function useSheetContext() {
  const context = React.useContext(SheetContext);
  if (!context) {
    throw new Error("Sheet components must be used within a Sheet provider");
  }
  return context;
}

interface SheetProps {
  children: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function Sheet({ children, open: controlledOpen, onOpenChange }: SheetProps) {
  const [internalOpen, setInternalOpen] = React.useState(false);
  const [side, setSide] = React.useState<SheetSide>("right");
  const dialogRef = React.useRef<HTMLDialogElement>(null);

  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const setOpen = React.useCallback(
    (value: boolean) => {
      if (!isControlled) setInternalOpen(value);
      onOpenChange?.(value);
    },
    [isControlled, onOpenChange],
  );

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  React.useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const handleClose = () => setOpen(false);
    dialog.addEventListener("close", handleClose);
    return () => dialog.removeEventListener("close", handleClose);
  }, [setOpen]);

  return (
    <SheetContext.Provider value={{ open, setOpen, dialogRef, side, setSide }}>
      {children}
    </SheetContext.Provider>
  );
}

interface SheetTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

const SheetTrigger = React.forwardRef<HTMLButtonElement, SheetTriggerProps>(
  ({ onClick, ...props }, ref) => {
    const { setOpen } = useSheetContext();
    return (
      <button
        ref={ref}
        onClick={(e) => {
          setOpen(true);
          onClick?.(e);
        }}
        {...props}
      />
    );
  },
);
SheetTrigger.displayName = "SheetTrigger";

const sheetVariants = cva(
  "fixed z-50 gap-4 border border-border/70 bg-[linear-gradient(180deg,color-mix(in_oklch,var(--color-card)_94%,transparent)_0%,color-mix(in_oklch,var(--color-background)_88%,black)_100%)] text-foreground shadow-[0_36px_80px_-32px_rgba(0,0,0,0.95)] transition-transform duration-300 ease-in-out backdrop-blur-xl",
  {
    variants: {
      side: {
        top: "inset-x-0 top-0 m-0 max-h-[80vh] w-full rounded-b-[2rem] border-b",
        right: "inset-y-0 right-0 m-0 h-full w-3/4 max-w-sm rounded-l-[2rem] border-l",
        bottom: "inset-x-0 bottom-0 m-0 max-h-[88vh] w-full rounded-t-[2rem] border-t",
        left: "inset-y-0 left-0 m-0 h-full w-3/4 max-w-sm rounded-r-[2rem] border-r",
      },
    },
    defaultVariants: {
      side: "right",
    },
  },
);

interface SheetContentProps
  extends React.HTMLAttributes<HTMLDialogElement>,
    VariantProps<typeof sheetVariants> {
  side?: SheetSide;
}

const SheetContent = React.forwardRef<HTMLDialogElement, SheetContentProps>(
  ({ className, children, side = "right", ...props }, ref) => {
    const { setOpen, dialogRef, setSide } = useSheetContext();

    React.useEffect(() => {
      setSide(side);
    }, [side, setSide]);

    const combinedRef = React.useCallback(
      (node: HTMLDialogElement | null) => {
        (dialogRef as React.MutableRefObject<HTMLDialogElement | null>).current = node;
        if (typeof ref === "function") ref(node);
        else if (ref) (ref as React.MutableRefObject<HTMLDialogElement | null>).current = node;
      },
      [dialogRef, ref],
    );

    const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
      if (e.target === e.currentTarget) {
        setOpen(false);
      }
    };

    return (
      <dialog
        ref={combinedRef}
        className={cn(
          sheetVariants({ side }),
          "overflow-hidden bg-transparent p-0 backdrop:bg-[color-mix(in_oklch,var(--color-background)_42%,black)]",
          className,
        )}
        onClick={handleBackdropClick}
        {...props}
      >
        <div className="relative h-full overflow-auto px-5 pb-6 pt-5">
          <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top,color-mix(in_oklch,var(--color-primary)_22%,transparent),transparent_70%)] opacity-90" />
          <div className="pointer-events-none absolute right-0 top-10 h-24 w-24 rounded-full bg-[color-mix(in_oklch,var(--color-secondary)_22%,transparent)] blur-3xl" />
          {children}
          <SheetClose className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full border border-border/80 bg-card/70 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring">
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </SheetClose>
        </div>
      </dialog>
    );
  },
);
SheetContent.displayName = "SheetContent";

const SheetHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col space-y-2 text-center sm:text-left", className)}
    {...props}
  />
));
SheetHeader.displayName = "SheetHeader";

const SheetFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props}
  />
));
SheetFooter.displayName = "SheetFooter";

const SheetTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn("text-lg font-semibold text-foreground", className)}
    {...props}
  />
));
SheetTitle.displayName = "SheetTitle";

const SheetDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
));
SheetDescription.displayName = "SheetDescription";

interface SheetCloseProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

const SheetClose = React.forwardRef<HTMLButtonElement, SheetCloseProps>(
  ({ onClick, ...props }, ref) => {
    const { setOpen } = useSheetContext();
    return (
      <button
        ref={ref}
        onClick={(e) => {
          setOpen(false);
          onClick?.(e);
        }}
        {...props}
      />
    );
  },
);
SheetClose.displayName = "SheetClose";

export {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetFooter,
  SheetTitle,
  SheetDescription,
  SheetClose,
  SHEET_SIDES,
};
export type { SheetSide };
