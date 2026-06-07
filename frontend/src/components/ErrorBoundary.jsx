import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(_error, _info) {
    // Errors are surfaced in the render fallback; no console logging in production
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-full flex items-center justify-center bg-base p-10">
          <div className="text-center max-w-md space-y-4">
            <div className="text-5xl">💥</div>
            <h2 className="text-xl font-bold text-txt">Something went wrong</h2>
            <p className="text-txt-secondary text-sm">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={this.handleReset}
              className="px-6 py-2.5 bg-accent text-white rounded-xl font-medium hover:opacity-90 transition"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
