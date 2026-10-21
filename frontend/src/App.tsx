import { useQuery } from "@tanstack/react-query";
import { Suspense, lazy } from "react";
import { Route, Routes } from "react-router";

import { AppShell } from "@/components/AppShell";
import { ProfileGate } from "@/hooks/profile";
import { RestTimerProvider } from "@/hooks/restTimer";
import { api } from "@/lib/api";
import ExercisesPage from "@/pages/ExercisesPage";
import HistoryPage from "@/pages/HistoryPage";
import PlanAssistantPage from "@/pages/PlanAssistantPage";
import SchedulePage from "@/pages/SchedulePage";
import SessionDetailPage from "@/pages/SessionDetailPage";
import SettingsPage from "@/pages/SettingsPage";
import TemplateEditorPage from "@/pages/TemplateEditorPage";
import TodayPage from "@/pages/TodayPage";
import WorkoutPage from "@/pages/WorkoutPage";
import { Spinner } from "@/components/ui/misc";

// Chart pages pull in Recharts; load them on demand so the workout screen stays light.
const AnalyticsPage = lazy(() => import("@/pages/AnalyticsPage"));
const ExerciseDetailPage = lazy(() => import("@/pages/ExerciseDetailPage"));

function Loading() {
  return (
    <div className="flex justify-center py-24">
      <Spinner />
    </div>
  );
}

function NotFound() {
  return <p className="py-20 text-center text-muted-foreground">Page not found.</p>;
}

export default function App() {
  return (
    <ProfileGate>
      <ProfileApp />
    </ProfileGate>
  );
}

function ProfileApp() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return (
    <RestTimerProvider sound={settings.data?.rest_timer_sound ?? true}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<TodayPage />} />
          <Route path="workout/:sessionId" element={<WorkoutPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="schedule/assistant" element={<PlanAssistantPage />} />
          <Route path="schedule/:templateId" element={<TemplateEditorPage />} />
          <Route path="exercises" element={<ExercisesPage />} />
          <Route
            path="exercises/:exerciseId"
            element={
              <Suspense fallback={<Loading />}>
                <ExerciseDetailPage />
              </Suspense>
            }
          />
          <Route path="history" element={<HistoryPage />} />
          <Route path="history/:sessionId" element={<SessionDetailPage />} />
          <Route
            path="stats"
            element={
              <Suspense fallback={<Loading />}>
                <AnalyticsPage />
              </Suspense>
            }
          />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </RestTimerProvider>
  );
}
