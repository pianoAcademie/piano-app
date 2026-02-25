import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { backendRequest } from "../lib/backend";
import type { UserOut } from "../lib/types";

export default async function HomePage(): Promise<never> {
  const token = cookies().get("access_token")?.value;
  if (!token) {
    redirect("/login");
  }

  const meResult = await backendRequest<UserOut>("/api/v1/auth/me", {}, token);
  if (!meResult.ok) {
    redirect("/login?error=Session%20expiree");
  }

  if (meResult.data.role === "admin") {
    redirect("/admin");
  }

  if (meResult.data.role === "client") {
    redirect("/dashboard");
  }

  redirect("/prof");
}
