import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";
import { getStorage } from "firebase/storage";
import { getAnalytics } from "firebase/analytics";

const firebaseConfig = {
    apiKey: "AIzaSyAsCmfgzL4hws7ebt5ld7UluR1m88cnumA",
    authDomain: "socialentangler-b92a8.firebaseapp.com",
    projectId: "socialentangler-b92a8",
    storageBucket: "socialentangler-b92a8.firebasestorage.app",
    messagingSenderId: "35366083327",
    appId: "1:35366083327:web:afe695c704cfff196d0aca",
    measurementId: "G-14E8SZMP8W"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);
export const auth = getAuth(app);
export const storage = getStorage(app);
export const googleProvider = new GoogleAuthProvider();
export default app;
