import { redirect } from "next/navigation";

// Entry point: send to the dashboard. The (console) layout bounces to /login if
// there is no authenticated session.
export default function Home() {
  redirect("/dashboard");
}
