import { Component } from "react";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * Last resort for a render that throws.
 *
 * Without one, any such error leaves a blank white page — the worst possible failure for
 * a dashboard whose whole job is telling you something is wrong. Strings are passed in
 * rather than read from i18n: whatever broke may well be the translation layer.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled render error", error, info);
  }

  render() {
    if (!this.state.error) {
      return this.props.children;
    }

    return (
      <div
        role="alert"
        className="min-h-screen bg-slate-50 flex items-center justify-center p-6"
      >
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-8 max-w-lg w-full text-center space-y-4">
          <AlertTriangle
            size={40}
            className="text-amber-500 mx-auto"
            aria-hidden="true"
          />
          <h1 className="text-lg font-bold text-slate-800">
            La interfaz ha fallado · The interface crashed
          </h1>
          <p className="text-sm text-slate-600">
            Recarga la página. Si vuelve a pasar, mira la consola del navegador y los logs
            del contenedor.
            <br />
            Reload the page. If it happens again, check the browser console and the
            container logs.
          </p>
          <pre className="text-left text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-x-auto text-slate-600">
            {String(this.state.error?.message ?? this.state.error)}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors"
          >
            <RotateCw size={16} aria-hidden="true" /> Recargar · Reload
          </button>
        </div>
      </div>
    );
  }
}
