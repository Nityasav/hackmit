"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * These must be written as literal `process.env.NEXT_PUBLIC_*` member reads.
 * Next.js substitutes the value at build time by matching that exact text, so
 * a computed lookup like `process.env[name]` is left alone and arrives in the
 * browser as undefined.
 */
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

const SETUP_HINT =
  "Set it in web/.env.local and restart the dev server. " +
  "Use the Supabase publishable/anon key, never a service-role key.";

/**
 * One client for the whole tab.
 *
 * Every call to createBrowserClient builds a new auth listener and storage
 * adapter, so calling it per component would multiply token refreshes.
 */
let browserClient: SupabaseClient | undefined;

export function getSupabaseClient(): SupabaseClient {
  if (!SUPABASE_URL) throw new Error(`NEXT_PUBLIC_SUPABASE_URL is missing. ${SETUP_HINT}`);
  if (!SUPABASE_ANON_KEY) throw new Error(`NEXT_PUBLIC_SUPABASE_ANON_KEY is missing. ${SETUP_HINT}`);

  browserClient ??= createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  return browserClient;
}

/** @deprecated Prefer getSupabaseClient. */
export const createClient = getSupabaseClient;
