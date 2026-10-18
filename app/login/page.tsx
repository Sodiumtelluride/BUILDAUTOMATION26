import { AuthError } from "next-auth"
import { redirect } from "next/navigation"
import { signIn } from "@/src/auth"

async function login(formData: FormData) {
  "use server"
  try {
    await signIn("credentials", {
      email: formData.get("email"),
      password: formData.get("password"),
      redirectTo: "/factory",
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

  return (
    <main className="mx-auto mt-24 w-full max-w-sm px-4">
      <h1 className="mb-6 text-2xl font-semibold">Log in</h1>
      <form action={login} className="flex flex-col gap-3">
        <input name="email" type="email" placeholder="Email" required className="rounded border px-3 py-2" />
        <input name="password" type="password" placeholder="Password" required className="rounded border px-3 py-2" />
        {error && <p className="text-sm text-red-600">Invalid email or password.</p>}
        <button type="submit" className="rounded bg-black px-3 py-2 text-white">
          Log in
        </button>
      </form>
    </main>
  )
}
