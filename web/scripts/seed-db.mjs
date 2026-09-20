// One-off loader: pushes the bundle fixtures into Postgres through
// seed_workspace(). Run once to move the demo content off JSON and into the
// database; after that the database is the source and the JSON is only a seed.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createClient } from "@supabase/supabase-js";

const here = dirname(fileURLToPath(import.meta.url));
const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const email = process.env.SEED_EMAIL;
const password = process.env.SEED_PASSWORD;

if (!url || !key || !email || !password) {
  console.error("need NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, SEED_EMAIL, SEED_PASSWORD");
  process.exit(1);
}

const supabase = createClient(url, key);
const { error: authError } = await supabase.auth.signInWithPassword({ email, password });
if (authError) {
  console.error("sign in failed:", authError.message);
  process.exit(1);
}

for (const name of ["sandbox", "mit"]) {
  const bundle = JSON.parse(readFileSync(join(here, "..", "..", "supabase", "seed", `${name}.json`), "utf8"));
  const { data, error } = await supabase.rpc("seed_workspace", { bundle });
  if (error) {
    console.error(`${name}: ${error.message}`);
    process.exit(1);
  }
  console.log(`seeded ${data}`);
}

await supabase.auth.signOut();
