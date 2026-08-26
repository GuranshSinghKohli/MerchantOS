"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchSession } from "@/lib/analytics";

/** Trusted store id from the session cookie via GET /api/v1/me. Never from the URL. */
export function useSessionStore() {
  return useQuery({
    queryKey: ["session-store"],
    queryFn: fetchSession,
  });
}
