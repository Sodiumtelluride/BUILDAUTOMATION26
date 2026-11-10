import { AuthError } from "next-auth"
import { redirect } from "next/navigation"
import { signIn } from "@/src/auth"
import SignInPage from "@/src/components/sign-in-page"

// Runs on the server when the form is submitted: Auth.js checks the email + password
async function login(formData: FormData) {
  "use server"
  try {
    await signIn("credentials", {
      // lowercase so "Arav@UMass.edu" matches the stored "arav@umass.edu"
      email: String(formData.get("email") ?? "").trim().toLowerCase(),
      password: formData.get("password"),
      redirectTo: "/dashboard",
    })
  } catch (error) {
    if (error instanceof AuthError) redirect("/login?error=1")
    throw error // signIn redirects by throwing on success
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>
}) {
  const { error } = await searchParams

  return <SignInPage action={login} error={Boolean(error)} />
}
