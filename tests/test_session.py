"""Phase bookkeeping tests. No application, registry or filesystem changes."""
import json
import unittest
from app.session import OperationSession


class OperationSessionTests(unittest.TestCase):
    def test_full_flow_serializable_and_snapshot_detached(self):
        operation=OperationSession('Fixture 应用')
        for phase in ('uninstall','scan','review','cleanup','complete'):
            snapshot=operation.transition(phase, selected=['one'])
        self.assertEqual(operation.phase,'complete')
        self.assertEqual([h['phase'] for h in snapshot['history']],
                         ['prepare','uninstall','scan','review','cleanup','complete'])
        snapshot['metadata']['selected'].append('tamper')
        self.assertEqual(operation.metadata['selected'],['one'])
        self.assertEqual(json.loads(json.dumps(operation.to_dict()))['phase'],'complete')

    def test_roundtrip_no_shared_mutable_metadata(self):
        source={'paths':['first']}
        operation=OperationSession('App',metadata=source)
        source['paths'].append('outside')
        self.assertEqual(operation.metadata,{'paths':['first']})
        operation.transition('uninstall')
        restored=OperationSession.from_dict(operation.to_dict())
        self.assertEqual(restored.to_dict(),operation.to_dict())
        restored.metadata['paths'].append('new')
        self.assertEqual(operation.metadata['paths'],['first'])

    def test_cannot_skip_review_or_uninstall(self):
        operation=OperationSession('App')
        with self.assertRaises(ValueError):
            operation.transition('cleanup')
        self.assertEqual(operation.phase,'prepare')
        operation.transition('uninstall')
        with self.assertRaises(ValueError):
            operation.transition('complete')
        self.assertEqual(operation.phase,'uninstall')

    def test_failure_is_terminal_from_every_active_phase(self):
        phases=['prepare','uninstall','scan','review','cleanup']
        for index,phase in enumerate(phases):
            operation=OperationSession('App')
            for target in phases[1:index+1]:
                operation.transition(target)
            operation.transition('failed','vendor error')
            self.assertEqual(operation.phase,'failed')
            with self.assertRaises(ValueError):
                operation.transition('prepare')

    def test_review_can_complete_without_extra_cleanup(self):
        operation=OperationSession('App')
        for phase in ('uninstall','scan','review','complete'):
            operation.transition(phase)
        with self.assertRaises(ValueError):
            operation.transition('cleanup')

    def test_nonserializable_metadata_rejected_before_transition(self):
        operation=OperationSession('App')
        with self.assertRaises(TypeError):
            operation.transition('uninstall',selected={1,2})
        self.assertEqual(operation.phase,'prepare')
        self.assertEqual(len(operation.history),1)

    def test_invalid_session_data_rejected(self):
        with self.assertRaises(ValueError):
            OperationSession('')
        with self.assertRaises(ValueError):
            OperationSession('App',phase='unknown')
        with self.assertRaises(ValueError):
            OperationSession('App',session_id='../escape')
        with self.assertRaises(ValueError):
            OperationSession.from_dict({'phase':'review'})


if __name__=='__main__':
    unittest.main()
