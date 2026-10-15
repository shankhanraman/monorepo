import { useState } from "react";
import "./App.css";
import { getApiKey } from "./auth/apiKey";
import SignInMenu from "./auth/SignInMenu";
import Me from "./me/Me";
import Profiles from "./profiles/Profiles";
import Users from "./users/Users";

export default function App() {
  // Saving/forgetting a key reloads the page, so this is stable while the page is open.
  const signedIn = !!getApiKey();
  // Bumped on user changes so Profiles reloads (owner names, delete cascades).
  const [usersVersion, setUsersVersion] = useState(0);

  return (
    <main className="app">
      <header className="app-header">
        <h1>API Key Lab</h1>
        <SignInMenu />
      </header>
      {signedIn ? <Me /> : <p className="muted">Browsing as guest. Add an API key to create, edit or delete.</p>}
      <Users canEdit={signedIn} onChange={() => setUsersVersion((v) => v + 1)} />
      <Profiles canEdit={signedIn} version={usersVersion} />
    </main>
  );
}
