import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { resetRestTimer } from "@/hooks/restTimer";
import { api } from "@/lib/api";
import { getProfileId, storeProfileId } from "@/lib/profile";
import { queryClient } from "@/lib/queryClient";
import type { Profile } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ProfileApi {
  profile: Profile;
  profiles: Profile[];
  switchProfile: (id: number) => void;
}

const ProfileContext = React.createContext<ProfileApi | null>(null);

export function useProfile(): ProfileApi {
  const ctx = React.useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside <ProfileGate>");
  return ctx;
}

const AVATAR_COLORS = ["bg-primary text-primary-foreground", "bg-info text-background", "bg-warning text-background"];

export function ProfileAvatar({ profile, className }: { profile: Profile; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-8 shrink-0 items-center justify-center rounded-full text-sm font-bold",
        AVATAR_COLORS[(profile.id - 1) % AVATAR_COLORS.length],
        className,
      )}
    >
      {profile.name.charAt(0).toUpperCase()}
    </span>
  );
}

function ProfilePicker({ profiles, onPick }: { profiles: Profile[]; onPick: (id: number) => void }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 pb-safe pt-safe">
      <img src="/icon.svg" alt="" className="size-14" />
      <h1 className="mt-5 text-[28px] font-bold tracking-tight">Who's training?</h1>
      <p className="mt-1 text-muted-foreground">Each person has their own plan and history.</p>
      <ul className="mt-8 w-full max-w-sm space-y-3">
        {profiles.map((p) => (
          <li key={p.id}>
            <button
              onClick={() => onPick(p.id)}
              className="flex w-full items-center gap-4 rounded-2xl border border-border bg-card p-4 text-left transition-colors hover:bg-elevated active:scale-[0.99]"
            >
              <ProfileAvatar profile={p} className="size-12 text-lg" />
              <span className="flex-1 text-lg font-semibold">{p.name}</span>
              <ChevronRight className="size-5 text-subtle" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Asks who is using the device, then renders the app for that person. */
export function ProfileGate({ children }: { children: React.ReactNode }) {
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: api.profiles, staleTime: Infinity });
  const [profileId, setProfileId] = React.useState(getProfileId);
  const navigate = useNavigate();

  const switchProfile = React.useCallback(
    (id: number) => {
      if (id === profileId) return;
      const switching = profileId !== null;
      storeProfileId(id);
      if (switching) {
        // Everything cached belongs to the previous person.
        resetRestTimer();
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "profiles" });
        navigate("/");
      }
      setProfileId(id);
    },
    [profileId, navigate],
  );

  if (profiles.isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (!profiles.data) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
        <p className="text-muted-foreground">Couldn't reach Workout Pal.</p>
        <Button variant="secondary" onClick={() => void profiles.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const profile = profiles.data.find((p) => p.id === profileId);
  if (!profile) return <ProfilePicker profiles={profiles.data} onPick={switchProfile} />;

  return (
    <ProfileContext.Provider value={{ profile, profiles: profiles.data, switchProfile }}>
      {/* Remount per person so no state from the previous profile lingers. */}
      <React.Fragment key={profile.id}>{children}</React.Fragment>
    </ProfileContext.Provider>
  );
}
