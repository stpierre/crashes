# Makefile
PYTHON_EXE = python2

all: check

help: # Display help
	@awk -F ':|##' \
		'/^[^\t].+?:.*?##/ {\
			printf "\033[36m%-30s\033[0m %s\n", $$1, $$NF \
		}' $(MAKEFILE_LIST)

check-format: ## Check code format
	@{ \
	set -euo pipefail ;\
	DIFF=`find . -name .eggs -prune -o -name \*.py -print0 | xargs -0 yapf -d -r` ;\
	if [ -n "$$DIFF" ] ;\
	then \
	echo -e "\nFormatting changes requested:\n" ;\
	echo "$$DIFF" ;\
	echo -e "\nRun 'make format' to automatically make changes.\n" ;\
	exit 1 ;\
	fi ;\
	}

format: ## Format code
	find . -name .eggs -prune -o -name \*.py -print0 | xargs -0 yapf -i -r

prospector: ## Run prospector
	find . -name .eggs -prune -o -name \*.py -print0 | xargs -0 prospector -s veryhigh

check: check-format prospector ## Check code format & lint

clean: ## Delete all generated artifacts
	$(RM) -rf dist __pycache__ *.egg-info
	find . -name "*.pyc" -delete

.PHONY: help check-format format pylint check clean
