import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ko from "./locales/ko.json";
import vi from "./locales/vi.json";

const savedLanguage = localStorage.getItem("itda-language");
const initialLanguage = savedLanguage === "vi" || savedLanguage === "ko"
  ? savedLanguage
  : navigator.language.toLowerCase().startsWith("vi") ? "vi" : "ko";

void i18n.use(initReactI18next).init({
  resources: { ko: { translation: ko }, vi: { translation: vi } },
  lng: initialLanguage,
  fallbackLng: "ko",
  interpolation: { escapeValue: false },
});

export async function changeLanguage(language: "ko" | "vi") {
  localStorage.setItem("itda-language", language);
  await i18n.changeLanguage(language);
  document.documentElement.lang = language;
}

document.documentElement.lang = initialLanguage;

export default i18n;

