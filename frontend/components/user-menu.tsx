"use client";

import { useSession, signOut } from "next-auth/react";

export function UserMenu() {
  const { data: session } = useSession();

  if (!session?.user) return null;

  const email = session.user.email ?? "";
  const name = session.user.name ?? email.split("@")[0];
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="flex items-center gap-3">
      {/* Avatar */}
      <div className="flex items-center gap-2">
        {session.user.image ? (
          <img
            src={session.user.image}
            alt={name}
            className="h-7 w-7 rounded-full"
            referrerPolicy="no-referrer"
          />
        ) : (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-orange-600 text-xs font-medium text-white">
            {initials}
          </div>
        )}
        <span className="hidden text-xs text-zinc-400 md:inline">{name}</span>
      </div>

      {/* Sign out */}
      <button
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="rounded px-2 py-1 text-xs text-zinc-500 transition-colors hover:text-zinc-200"
      >
        Sign out
      </button>
    </div>
  );
}
