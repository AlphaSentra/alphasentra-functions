"""
Reusable animated gradient background styles.
"""

ANIMATED_GRADIENT_BACKGROUND_CSS = """
        @keyframes fade-in {
          0%, 100% { opacity: 0; }
          50% { opacity: 1; }
        }

        @keyframes fade-out {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }

        .animated-gradient-background {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background-color: #000;
          z-index: 0;
        }

        .form-background-wrapper {
          position: relative;
          height: 100vh;
          overflow: hidden;
          background-color: #000;
        }

        .form-foreground {
          position: relative;
          z-index: 1;
        }

        .animated-gradient-background::before,
        .animated-gradient-background::after {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background-size: 100% 100%;
          background-repeat: no-repeat;
        }

        .animated-gradient-background::before {
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(120, 50, 220, 0.4), transparent);
          opacity: 1;
          animation: fade-out 10s infinite;
        }

        .animated-gradient-background::after {
          background-image: radial-gradient(ellipse 80% 50% at 50% 120%, rgba(0, 255, 255, 0.4), transparent);
          opacity: 0;
          animation: fade-in 10s infinite;
        }
"""
