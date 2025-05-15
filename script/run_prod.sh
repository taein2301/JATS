export JATS_HOME="$HOME/JATS"

source $JATS_HOME/jats_venv/bin/activate
nohup python $JATS_HOME/main.py upbit prod &
