# Mnemo website (Firebase)

1. Create a project at https://console.firebase.google.com (free Spark plan is enough).
2. **Build → Authentication → Get started → Google → Enable.**
3. **Build → Firestore Database → Create database** (production mode, any region).
4. **Project settings → Your apps → Web (`</>`)** → register an app → copy the config values into `public/firebase-config.js`.
5. Put your project id in `.firebaserc`, then claim the site name and deploy:

```bash
npm install -g firebase-tools
firebase login
cd website && firebase hosting:sites:create mnemo && firebase deploy
```

Your site is live at `https://mnemoai.web.app`. The installer is also served at `https://<project-id>.web.app/install`.
After you add a custom domain, add it under Authentication → Settings → Authorized domains.

6. The app reads the same `public/firebase-config.js`, so once it's filled in, sign-in works in the app too.
   Enable **Email/Password** as well as **Google** under Authentication → Sign-in method.
