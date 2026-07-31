import { Coffee } from "lucide-react";

/**
 * Footer portado de la demo de la web (`.pp-footer` / `.pp-coffee`): el enlace de
 * "invítame un café" deja de ser la píldora amarilla de Buy Me a Coffee y pasa a la
 * misma familia de pills azules que las acciones de la cabecera, rellenándose en hover.
 */
export default function Footer({ t }) {
  return (
    <footer className="bg-white border-t border-slate-200 mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-[22px] flex flex-wrap justify-between items-center gap-[14px]">
        <p className="text-[13px] font-medium text-slate-400">
          &copy; {new Date().getFullYear()}{" "}
          <a
            href="https://github.com/KN990x"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            KN990x
          </a>
        </p>

        <a
          href="https://buymeacoffee.com/kn990x"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-[7px] px-[15px] py-2 rounded-[10px] border border-blue-600/30 bg-blue-600/[0.08] text-blue-600 text-[13px] font-semibold transition-colors hover:bg-blue-600 hover:border-blue-600 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <Coffee size={15} />
          {t("footer.tip_me")}
        </a>
      </div>
    </footer>
  );
}
