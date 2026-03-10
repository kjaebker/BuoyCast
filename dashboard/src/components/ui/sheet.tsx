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
    [isControlled, onOpenChange]
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
  }
);
SheetTrigger.displayName = "SheetTrigger";

const sheetVariants = cva(
  "fixed z-50 gap-4 bg-background text-foreground p-6 shadow-lg transition-transform duration-300 ease-in-out",
  {
    variants: {
      side: {
        top: "inset-x-0 top-0 m-0 max-h-[80vh] w-full border-b",
        right: "inset-y-0 right-0 m-0 h-full w-3/4 max-w-sm border-l",
        bottom: "inset-x-0 bottom-0 m-0 max-h-[80vh] w-full border-t",
        left: "inset-y-0 left-0 m-0 h-full w-3/4 max-w-sm border-r",
      },
    },
    defaultVariants: {
      side: "right",
    },
  }
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
      [dialogRef, ref]
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
          "backdrop:bg-black/80 p-0",
          className
        )}
        onClick={handleBackdropClick}
        {...props}
      >
        <div className="flex h-full flex-col p-6">
          {children}
          <SheetClose className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
            <X className="h-4 w-4" />
            <span className="sr-only">Close</span>
          </SheetClose>
        </div>
      </dialog>
    );
  }
);
SheetContent.displayName = "SheetContent";

const SheetHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "flex flex-col space-y-2 text-center sm:text-left",
      className
    )}
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
    className={cn(
      "flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2",
      className
    )}
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
  }
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
