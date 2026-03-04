import { redirect } from "next/navigation";

export default function ClientHomePage(): never {
  redirect("/client?tab=home");
}
