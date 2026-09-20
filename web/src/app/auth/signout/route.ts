import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { RETURNING_COOKIE } from "@/lib/session-cookie";

/** Signing out changes state, so it is a POST rather than a link. */
export async function POST(request: NextRequest) {
  const supabase = await createClient();
  await supabase.auth.signOut();

  const response = NextResponse.redirect(new URL("/login", request.url), { status: 303 });
  // A shared machine should not imply who used it last.
  response.cookies.set(RETURNING_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
