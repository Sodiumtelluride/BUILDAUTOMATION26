import { redirect } from "next/navigation"
import { auth } from "@/src/auth"

// Home page: signed in -> the console, not signed in -> the sign-in page
export default async function Home() {
  const session = await auth()
  redirect(session ? "/dashboard" : "/login")
}
