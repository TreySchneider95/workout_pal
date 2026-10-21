import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronRight, Clock, History as HistoryIcon, ListChecks, Weight } from "lucide-react";
import { Link } from "react-router";

import { EmptyState, PageHeader } from "@/components/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { compactNumber, dateWithWeekday, minutesText } from "@/lib/format";
import type { SessionSummary } from "@/lib/types";

const PAGE = 20;

function monthLabel(iso: string) {
  const [y, m] = iso.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export function SessionCard({ session }: { session: SessionSummary }) {
  return (
    <Link to={`/history/${session.id}`} className="block">
      <Card className="p-4 transition-colors hover:bg-elevated sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm text-muted-foreground">{dateWithWeekday(session.performed_on)}</div>
            <h3 className="truncate text-lg font-semibold">{session.name}</h3>
          </div>
          <ChevronRight className="mt-1 size-5 shrink-0 text-subtle" />
        </div>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-4" /> {minutesText(session.duration_minutes)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <ListChecks className="size-4" /> {session.completed_sets} sets · {session.exercises_completed} exercises
          </span>
          {session.volume > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <Weight className="size-4" /> {compactNumber(session.volume)} lb volume
            </span>
          )}
        </div>
        <ul className="grid grid-cols-1 mt-3 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {session.exercises
            .filter((e) => e.best)
            .slice(0, 6)
            .map((e) => (
              <li key={e.exercise_id} className="flex justify-between gap-3">
                <span className="truncate text-muted-foreground">{e.exercise_name}</span>
                <span className="tabular shrink-0 font-medium">{e.best}</span>
              </li>
            ))}
        </ul>
        {session.notes && <p className="mt-3 line-clamp-2 text-sm italic text-muted-foreground">“{session.notes}”</p>}
      </Card>
    </Link>
  );
}

export default function HistoryPage() {
  const history = useInfiniteQuery({
    queryKey: ["history"],
    queryFn: ({ pageParam }) => api.history(pageParam, PAGE),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0);
      return loaded < last.total ? loaded : undefined;
    },
  });

  const items = history.data?.pages.flatMap((p) => p.items) ?? [];
  const total = history.data?.pages[0]?.total ?? 0;
  const groups: { month: string; items: SessionSummary[] }[] = [];
  items.forEach((s) => {
    const month = monthLabel(s.performed_on);
    const last = groups[groups.length - 1];
    if (last?.month === month) last.items.push(s);
    else groups.push({ month, items: [s] });
  });

  return (
    <div>
      <PageHeader title="History" subtitle={total ? `${total} workout${total === 1 ? "" : "s"} completed` : undefined} />
      {history.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : !items.length ? (
        <EmptyState icon={HistoryIcon} title="No workouts yet">
          Finished workouts appear here with every set you recorded.
        </EmptyState>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => (
            <section key={g.month}>
              <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">{g.month}</h2>
              <div className="space-y-3">
                {g.items.map((s) => (
                  <SessionCard key={s.id} session={s} />
                ))}
              </div>
            </section>
          ))}
          {history.hasNextPage && (
            <Button variant="secondary" className="w-full" onClick={() => history.fetchNextPage()} disabled={history.isFetchingNextPage}>
              {history.isFetchingNextPage ? "Loading…" : "Load more"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
