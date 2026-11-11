"""Composition of existing PG02 outcome and PG03 C3 strategy; candidate-only.

No synthetic receipt authorizes production dispatch or checkpoint closure.
"""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'pg02'))
from test_pg02_classifier_v1 import s as snapshot, m as catalog, pg01_binding
from pg02_classification_outcome_v1 import classify_with_outcome
from test_pg03_strategy_v1 import contract, s as stack, kw as strategy_inputs
from pg03_strategy_v1 import prepare_strategy, StrategyBlocked

mapping=copy.deepcopy(catalog)
mapping['front_kind_domains']['UI_VISUAL']=['STD-BE']
mapping['domain_stack_layers']['STD-BE']=['BACKEND']
binding=copy.deepcopy(pg01_binding)
binding['architecture_profile']['active_layers']=['BACKEND']
classification=classify_with_outcome(copy.deepcopy(snapshot),mapping,pg01_binding=binding)
assert classification['decision']=='CANDIDATE_ONLY' and classification['dispatch_allowed'] is False
assert classification['candidate']['scopes'][0]['candidate_domains']==['STD-BE']
args=copy.deepcopy(strategy_inputs)
args['classification']=classification
result=prepare_strategy(**args)
assert result==prepare_strategy(**copy.deepcopy(args))
assert result['status']=='CANDIDATE_NOT_ADMITTED'
assert result['handoff_allowed'] is False and result['production_authority'] is False
for mutation in ('forged_pass','blocked_scope','missing_classification'):
    bad=copy.deepcopy(args)
    if mutation=='forged_pass':bad['classification']['status']='PASS'
    elif mutation=='blocked_scope':bad['classification']['candidate']['scopes'][0]['state']='BLOCKED'
    else: bad['classification']=None
    try: prepare_strategy(**bad)
    except (StrategyBlocked,ValueError,TypeError):pass
    else:raise AssertionError('unexpected admission:'+mutation)
print('PG02_PG03_C3_CHAIN_PASS positive_candidate=1 negatives=3 authority=0')
