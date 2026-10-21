import { Check, ChevronsUpDown } from "lucide-react";

import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { ProfileAvatar, useProfile } from "@/hooks/profile";
import { cn } from "@/lib/utils";

/** Shows who is training and lets you switch. `compact` is the avatar-only phone header version. */
export function ProfileSwitcher({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { profile, profiles, switchProfile } = useProfile();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {compact ? (
          <button aria-label={`Profile: ${profile.name}. Switch profile`} className={cn("flex size-11 items-center justify-center rounded-xl hover:bg-muted", className)}>
            <ProfileAvatar profile={profile} />
          </button>
        ) : (
          <button className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-muted", className)}>
            <ProfileAvatar profile={profile} />
            <span className="min-w-0 flex-1 truncate text-[15px] font-medium">{profile.name}</span>
            <ChevronsUpDown className="size-4 text-subtle" />
          </button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={compact ? "end" : "start"}>
        {profiles.map((p) => (
          <DropdownMenuItem key={p.id} onSelect={() => switchProfile(p.id)}>
            <ProfileAvatar profile={p} className="size-7 text-xs" />
            <span className="flex-1">{p.name}</span>
            {p.id === profile.id && <Check className="!text-primary" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
