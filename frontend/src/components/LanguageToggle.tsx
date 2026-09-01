import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { changeLanguage } from "../i18n";


export default function LanguageToggle() {
  const { i18n } = useTranslation();
  const current = i18n.resolvedLanguage === "vi" ? "vi" : "ko";

  return (
    <div className="language-toggle" role="group" aria-label="Language">
      <Languages size={16} aria-hidden="true" />
      {(["ko", "vi"] as const).map((language) => (
        <button
          key={language}
          type="button"
          className={current === language ? "active" : ""}
          aria-pressed={current === language}
          onClick={() => void changeLanguage(language)}
        >
          {language === "ko" ? "한국어" : "Tiếng Việt"}
        </button>
      ))}
    </div>
  );
}

