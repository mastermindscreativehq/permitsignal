import "server-only";

import { createClient } from "@supabase/supabase-js";

// Server-only Supabase client. SUPABASE_KEY is a secret key (see
// backend .env / supabase/migrations/0001_create_leads_table.sql) and
// must never reach the browser. Importing "server-only" makes any
// accidental import from a Client Component fail the build instead of
// silently bundling the secret. Every read of this client happens from
// a Server Component or Route Handler -- the browser only ever sees
// the JSON those already produce.
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_KEY;

if (!SUPABASE_URL || !SUPABASE_KEY) {
  throw new Error(
    "SUPABASE_URL and SUPABASE_KEY must be set in dashboard/.env.local " +
      "to load real Provo Administrative Services Finance leads."
  );
}

export const LEADS_TABLE = process.env.SUPABASE_LEADS_TABLE || "leads";

export const supabaseServer = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: false },
});
