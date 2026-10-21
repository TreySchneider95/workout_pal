import { BarChart3, CalendarDays, Dumbbell, History, House, Settings } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router";

import { ProfileSwitcher } from "@/components/ProfileSwitcher";
import { RestTimerBar } from "@/components/RestTimerBar";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Today", icon: House, end: true },
  { to: "/schedule", label: "Plan", icon: CalendarDays },
  { to: "/exercises", label: "Exercises", icon: Dumbbell },
  { to: "/history", label: "History", icon: History },
  { to: "/stats", label: "Stats", icon: BarChart3 },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img src="/icon.svg" alt="" className="size-8" />
      <span className="text-[17px] font-bold tracking-tight">Workout Pal</span>
    </div>
  );
}

export function AppShell() {
  const location = useLocation();
  const inWorkout = location.pathname.startsWith("/workout/");

  return (
    <div className="min-h-dvh">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-border bg-card/40 px-4 py-6 lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        <nav className="mt-8 flex flex-col gap-1">
          {[...NAV, { to: "/settings", label: "Settings", icon: Settings, end: false }].map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
                  isActive && "bg-muted text-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn("size-5", isActive && "text-primary")} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto border-t border-border pt-4">
          <ProfileSwitcher />
        </div>
      </aside>

      <main
        className={cn(
          "w-full px-4 lg:pl-[calc(16rem+2.5rem)] lg:pr-10",
          inWorkout ? "pb-40 lg:pb-28" : "pb-32 pt-safe lg:pb-12",
        )}
      >
        <div className="mx-auto w-full max-w-3xl lg:max-w-5xl">
          <Outlet />
        </div>
      </main>

      <RestTimerBar />

      {/* Phone bottom navigation */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/90 pb-safe backdrop-blur-lg lg:hidden">
        <div className="mx-auto grid max-w-lg grid-cols-5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium text-subtle transition-colors",
                  isActive && "text-foreground",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn("size-[22px]", isActive && "text-primary")} strokeWidth={isActive ? 2.4 : 2} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  action,
  back,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  back?: React.ReactNode;
}) {
  return (
    <header className="flex items-end justify-between gap-3 pb-5 pt-5 lg:pt-10">
      <div className="min-w-0">
        {back}
        {subtitle && <p className="text-sm font-medium text-muted-foreground">{subtitle}</p>}
        <h1 className="truncate text-[28px] font-bold leading-tight tracking-tight lg:text-3xl">{title}</h1>
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </header>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-muted">
        <Icon className="size-6 text-muted-foreground" />
      </div>
      <div className="font-semibold">{title}</div>
      {children && <div className="max-w-sm text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function StatTile({ label, value, hint, className }: { label: string; value: React.ReactNode; hint?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-2xl border border-border bg-card p-4", className)}>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="tabular mt-1.5 text-2xl font-bold tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-subtle">{hint}</div>}
    </div>
  );
}
