import * as React from "react";
import { createPortal } from "react-dom";
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
    if (!open || typeof document === "undefined") return;

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, setOpen]);

  return (
    <SheetContext.Provider value={{ open, setOpen, side, setSide }}>
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

const sheetPositionVariants = cva("flex h-full w-full p-3 sm:p-4", {
  variants: {
    side: {
      top: "items-start justify-center",
      right: "items-stretch justify-end",
      bottom: "items-center justify-center",
      left: "items-stretch justify-start",
    },
  },
  defaultVariants: {
    side: "right",
  },
});

const sheetPanelVariants = cva(
  "relative flex w-full flex-col overflow-hidden border border-border/70 bg-[linear-gradient(180deg,color-mix(in_oklch,var(--color-card)_95%,transparent)_0%,color-mix(in_oklch,var(--color-background)_90%,black)_100%)] text-foreground shadow-[0_36px_80px_-32px_rgba(0,0,0,0.95)] backdrop-blur-xl",
  {
    variants: {
      side: {
        top: "max-h-[calc(100dvh-1.5rem)] max-w-[46rem] rounded-[2rem]",
        right: "h-full max-w-[24rem] rounded-[2rem] sm:rounded-l-[2rem] sm:rounded-r-none",
        bottom: "max-h-[calc(100dvh-1.5rem)] max-w-[42rem] rounded-[2rem]",
        left: "h-full max-w-[24rem] rounded-[2rem] sm:rounded-l-none sm:rounded-r-[2rem]",
      },
    },
    defaultVariants: {
      side: "right",
    },
  },
);

interface SheetContentProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof sheetPanelVariants> {
  side?: SheetSide;
}

const SheetContent = React.forwardRef<HTMLDivElement, SheetContentProps>(
  ({ className, children, side = "right", ...props }, ref) => {
    const { open, setOpen, setSide } = useSheetContext();

    React.useEffect(() => {
      setSide(side);
    }, [side, setSide]);

    if (!open || typeof document === "undefined") {
      return null;
    }

    const content = (
      <div
        className="dark fixed inset-0 z-50 bg-[color-mix(in_oklch,var(--color-background)_42%,black)]"
        onClick={() => setOpen(false)}
      >
        <div className={sheetPositionVariants({ side })}>
          <div
            ref={ref}
            className={cn(sheetPanelVariants({ side }), className)}
            onClick={(event) => event.stopPropagation()}
            {...props}
          >
            <div className="relative flex max-h-[calc(100dvh-1.5rem)] flex-1 flex-col overflow-y-auto px-5 pb-6 pt-6 sm:px-6 sm:pb-7 sm:pt-7">
              <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--color-primary)_18%,transparent)_0%,color-mix(in_oklch,var(--color-primary)_10%,transparent)_30%,transparent_78%)] opacity-75 blur-[2px]" />
              <div className="pointer-events-none absolute right-0 top-10 h-24 w-24 rounded-full bg-[color-mix(in_oklch,var(--color-secondary)_18%,transparent)] blur-3xl" />
              {children}
              <SheetClose className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full border border-border/80 bg-card/70 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-2 focus:ring-ring">
                <X className="h-4 w-4" />
                <span className="sr-only">Close</span>
              </SheetClose>
            </div>
          </div>
        </div>
      </div>
    );

    return createPortal(content, document.body);
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

