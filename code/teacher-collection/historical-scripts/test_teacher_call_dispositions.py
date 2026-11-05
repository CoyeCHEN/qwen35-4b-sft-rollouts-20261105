import unittest
from teacher_call_dispositions import dispositions

def call(ident,status='stop',content=None,retry=None,source='agent',chunks=None):
 return dict(call_id=ident,source=source,status=status,retry_of=retry,native_response=dict(stopReason=status,content=content or []),chunks=chunks or [])

class DispositionsTest(unittest.TestCase):
 def test_empty_503_then_normal_native_retry_is_not_an_invented_target(self):
  x=dispositions([call('a','error'),call('b',retry='a',content=[dict(type='text',text='done')])])
  self.assertEqual(x[0]['disposition'],'RECOVERED_EMPTY_TRANSPORT_CALL_NO_ASSISTANT_TARGET');self.assertEqual(x[0]['recovered_by_call_id'],'b')
  self.assertEqual(x[1]['disposition'],'ASSISTANT_TARGET')
 def test_partial_thinking_error_and_partial_tools_are_never_silently_omitted(self):
  for first in [call('a','error',content=[dict(type='thinking',thinking='partial')]),call('a','error',chunks=[dict(choices=[dict(delta=dict(tool_calls=[dict(index=0)]))])])]:
   self.assertEqual(dispositions([first,call('b',retry='a')])[0]['disposition'],'ASSISTANT_TARGET')
 def test_multiple_retry_attempts_remain_accounted(self):
  x=dispositions([call('a','error'),call('b','error',retry='a'),call('c',retry='b')]);self.assertEqual([r['recovered_by_call_id'] for r in x],['c','c',None])
 def test_unrecovered_and_genuinely_empty_normal_response_differ(self):
  self.assertEqual(dispositions([call('a','error')])[0]['disposition'],'UNRECOVERED_EMPTY_CALL')
  self.assertEqual(dispositions([call('a')])[0]['disposition'],'ASSISTANT_TARGET')
 def test_retry_cross_source_and_ambiguity_fail_explicitly(self):
  for values in [[call('a','error'),call('b',retry='a',source='compaction')],[call('a','error'),call('b',retry='a'),call('c',retry='a')]]:
   with self.assertRaises(ValueError):dispositions(values)

if __name__=='__main__':unittest.main()
