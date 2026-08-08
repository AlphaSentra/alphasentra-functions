.PHONY: sync-plotlyjs

sync-plotlyjs:
	@python3 -c "import plotly, os, shutil; src=os.path.join(os.path.dirname(plotly.__file__), 'package_data', 'plotly.min.js'); dst=os.path.join(os.getcwd(), 'static', 'plotly.min.js'); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst); print(f'Synced plotly.js {plotly.__version__} -> {dst}')"
