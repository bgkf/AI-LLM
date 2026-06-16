export interface OktaUser {
  status: string;
  lastLogin: string | null;
}

export interface OktaError {
  error: string;
}

export function isOktaError(v: OktaUser | OktaError | null): v is OktaError {
  return v !== null && "error" in v;
}

export async function getOktaUser(email: string, token: string): Promise<OktaUser | OktaError | null> {
  const url = `https://COMPANY.okta.com/api/v1/users?q=${encodeURIComponent(email)}&limit=1`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: {
        Authorization: `SSWS ${token}`,
        Accept: "application/json",
      },
    });
  } catch (err) {
    return { error: `Network error: ${err}` };
  }

  if (res.status === 401) return { error: "Okta token invalid or expired — regenerate in Okta Admin → Security → API → Tokens" };
  if (!res.ok) return { error: `Okta API ${res.status}` };

  const users = await res.json() as Array<{
    status: string;
    lastLogin?: string | null;
  }>;

  if (!users.length) return null;

  return {
    status: users[0].status,
    lastLogin: users[0].lastLogin ?? null,
  };
}
