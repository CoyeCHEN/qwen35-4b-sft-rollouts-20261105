import copy
import json
import sys
import unittest
from pathlib import Path
from sft import qwen35 as c

TOOLS=[dict(type='function', function=dict(name='bash', description='Run a shell command', parameters=dict(type='object', properties=dict(command=dict(type='string')), required=['command'])))]


class CodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        if not os.environ.get('QWEN35_MODEL_PATH'):raise unittest.SkipTest('Set QWEN35_MODEL_PATH to run pinned native tokenizer goldens')
        cls.tok=c.load_tokenizer()

    def check(self, messages, scope='current', tools=None):
        row,meta=c.encode(self.tok,messages,tools,scope=scope)
        text=self.tok.decode(row['input_ids']);active=self.tok.decode([x for x in row['labels'] if x!=-100])
        self.assertTrue(active.endswith('<|im_end|>\n'))
        self.assertNotIn('USER_ONLY',active);self.assertNotIn('SYSTEM_ONLY',active);self.assertNotIn('OBS_ONLY',active)
        normalized = [c.normalize_message(m) for m in messages]
        rendered = self.tok.apply_chat_template(normalized, tools=tools, tokenize=False,
            add_generation_prompt=False, enable_thinking=True)
        if scope == 'current':
            prefix = self.tok.apply_chat_template(normalized[:-1], tools=tools, tokenize=False,
                add_generation_prompt=True, enable_thinking=True)
            prefix_ids = self.tok.apply_chat_template(normalized[:-1], tools=tools, tokenize=True,
                return_dict=False, add_generation_prompt=True, enable_thinking=True)
            self.assertTrue(rendered.startswith(prefix))
            expected = prefix_ids + self.tok.encode(rendered[len(prefix):], add_special_tokens=False)
            self.assertEqual(row['input_ids'][:len(prefix_ids)], prefix_ids)
        else:
            expected = self.tok.encode(rendered, add_special_tokens=False)
        self.assertEqual(row['input_ids'], expected)
        self.assertEqual(text, rendered)
        return row,meta,text,active

    def batch(self):
        return [dict(role='system',content='SYSTEM_ONLY'),dict(role='user',content='USER_ONLY'),
                dict(role='assistant',content=[dict(type='thinking',thinking='HISTORY_THINK'),dict(type='text',text='BEFORE_TEXT '),dict(type='toolCall',id='call-1',name='bash',arguments={'command':'printf 42'}),dict(type='text',text='AFTER_TEXT')]),
                dict(role='toolResult',toolCallId='call-1',content=[dict(type='text',text='OBS_ONLY:42')]),
                dict(role='assistant',reasoning_content='CURRENT_THINK',content='FINAL_BODY:42')]

    def test_single_and_nonthinking(self):
        _,_,text,active=self.check([dict(role='user',content='USER_ONLY'),dict(role='assistant',content='FINAL_BODY')])
        self.assertIn('<think>\n\n</think>',text);self.assertIn('FINAL_BODY',active)

    def test_thinking_tool_and_surrounding_body(self):
        row,meta,text,active=self.check(self.batch(),tools=TOOLS)
        for s in ['HISTORY_THINK','BEFORE_TEXT','AFTER_TEXT','printf 42']:self.assertIn(s,text);self.assertNotIn(s,active)
        self.assertLess(text.index('BEFORE_TEXT'),text.index('AFTER_TEXT'))
        for s in ['CURRENT_THINK','FINAL_BODY']:self.assertIn(s,active)
        self.assertEqual(meta['linkage'][0]['id'],'call-1')

    def test_tool_target_is_supervised(self):
        _,meta,_,active=self.check(self.batch()[:3],tools=TOOLS)
        for s in ['HISTORY_THINK','BEFORE_TEXT','AFTER_TEXT','<function=bash>','printf 42']:self.assertIn(s,active)
        self.assertEqual(meta['target_pending_tool_ids'],['call-1'])

    def test_multiturn_and_all_assistant(self):
        m=self.batch();m[4]['tool_calls']=[dict(id='call-2',type='function',function=dict(name='bash',arguments=json.dumps({'command':'printf 43'})))]
        m.extend([dict(role='tool',tool_call_id='call-2',content='OBS_ONLY:43'),dict(role='assistant',reasoning_content='LAST_THINK',content='DONE')])
        _,meta,text,active=self.check(m,tools=TOOLS)
        self.assertEqual(len(meta['linkage']),2);self.assertIn('LAST_THINK',active);self.assertNotIn('CURRENT_THINK',active)
        _,_,_,active=self.check(m,scope='all_assistant',tools=TOOLS)
        self.assertIn('CURRENT_THINK',active);self.assertIn('HISTORY_THINK',active)

    def test_compaction_uses_actual_request(self):
        messages=[dict(role='system',content='SYSTEM_ONLY'),dict(role='user',content='RECORDED_COMPACTION_SUMMARY + USER_ONLY'),dict(role='assistant',reasoning_content='POST_COMPACTION_THINK',content='DONE')]
        call=dict(context_fidelity='provider_payload',request_messages=messages[:-1],assistant_response=messages[-1],provider_payload={'messages':messages[:-1]})
        row,meta=c.encode_call(self.tok,call);text=self.tok.decode(row['input_ids'])
        self.assertIn('RECORDED_COMPACTION_SUMMARY',text);self.assertNotIn('UNCOMPRESSED_OLD_HISTORY',text)

    def test_long_history_and_no_silent_truncation(self):
        m=self.batch();m[3]['content'][0]['text']='OBS_ONLY '+ ''.join(f'line {i}: value {i*17}\n'for i in range(6000))
        row,_,text,_=self.check(m,tools=TOOLS);self.assertGreater(len(row['input_ids']),65536)
        with self.assertRaisesRegex(ValueError,'EXCEEDS_CUTOFF_NO_TRUNCATION'):c.encode(self.tok,m,TOOLS,cutoff=65536)

    def test_bad_tool_linkage_rejected(self):
        m=self.batch();m[3]['toolCallId']='wrong'
        with self.assertRaisesRegex(ValueError,'Orphan'):c.encode(self.tok,m,TOOLS)

    def test_parallel_results_require_representable_order(self):
        messages=[dict(role='user',content='USER_ONLY'),dict(role='assistant',content='',tool_calls=[
            dict(id=ident,type='function',function=dict(name='bash',arguments={'command':command}))
            for ident,command in [('parallel-1','printf 1'),('parallel-2','printf 2')]]),
            dict(role='tool',tool_call_id='parallel-1',content='OBS_ONLY:1'),
            dict(role='tool',tool_call_id='parallel-2',content='OBS_ONLY:2'),
            dict(role='assistant',content='DONE')]
        _,meta,_,_=self.check(messages,tools=TOOLS)
        self.assertEqual([x['id']for x in meta['linkage']],['parallel-1','parallel-2'])
        messages[2],messages[3]=messages[3],messages[2]
        with self.assertRaisesRegex(ValueError,'Tool result order'):c.encode(self.tok,messages,TOOLS)

    def test_native_historical_thinking_drop_rejected(self):
        m=[dict(role='user',content='FIRST_USER'),dict(role='assistant',content='EARLIER_BODY',reasoning_content='EARLIER_THINK'),dict(role='user',content='NEXT_USER'),dict(role='assistant',content='DONE')]
        with self.assertRaisesRegex(ValueError,'HISTORY_PROJECTION_REQUIRES_REVIEW'):c.encode(self.tok,m)

    def test_original_argument_order_beats_sorted_canonical(self):
        m=self.batch();m[2]=c.normalize_message(m[2]);m[3]=c.normalize_message(m[3])
        m[2]['tool_calls'][0]['function']['arguments']={'z_last_name':1,'a_first_name':2}
        original=copy.deepcopy(m[:-1]);original[2]['tool_calls'][0]['function']['arguments']='{"z_last_name":1,"a_first_name":2}'
        normalized=json.loads(json.dumps(m[:-1],sort_keys=True))
        row,meta=c.encode_call(self.tok,dict(context_fidelity='provider_payload',request_messages=normalized,
            assistant_response=m[-1],provider_payload=dict(messages=original,tools=TOOLS)))
        text=self.tok.decode(row['input_ids'])
        self.assertLess(text.index('<parameter=z_last_name>'),text.index('<parameter=a_first_name>'))
        self.assertTrue(meta['canonical_context_semantically_equal'])

    def task_calls(self,messages):
        return [dict(call_id='decision-'+str(i),context_fidelity='provider_payload',
            request_messages=copy.deepcopy(messages[:i]),assistant_response=copy.deepcopy(message),
            provider_payload=dict(messages=copy.deepcopy(messages[:i]),tools=copy.deepcopy(TOOLS)))
            for i,message in enumerate(messages)if message['role']=='assistant']

    def test_complete_task_supervises_each_real_target_once(self):
        calls=self.task_calls(self.batch());original=copy.deepcopy(calls)
        row,meta=c.encode_multiturn_task(self.tok,calls)
        active=self.tok.decode([x for x in row['labels']if x!=-100])
        for text in ('HISTORY_THINK','BEFORE_TEXT','AFTER_TEXT','CURRENT_THINK','FINAL_BODY'):
            self.assertIn(text,active)
        for text in ('SYSTEM_ONLY','USER_ONLY','OBS_ONLY'):
            self.assertNotIn(text,active)
        self.assertEqual(len(meta['decision_mapping']),2)
        self.assertEqual(meta['loss_tokens'],sum(b-a for a,b in meta['supervised_ranges']))
        self.assertTrue(meta['original_request_prefixes_verified'])
        self.assertEqual(calls,original)

    def test_task_rejects_rewritten_observation_and_schema(self):
        messages=self.batch();messages[4]['tool_calls']=[dict(id='call-2',type='function',
            function=dict(name='bash',arguments={'command':'printf 43'}))]
        messages.extend([dict(role='tool',tool_call_id='call-2',content='OBS_ONLY:43'),
                         dict(role='assistant',reasoning_content='LAST_THINK',content='DONE')])
        calls=self.task_calls(messages)
        c.encode_multiturn_task(self.tok,calls)
        changed=copy.deepcopy(calls)
        changed[-1]['provider_payload']['messages'][3]['content'][0]['text']='CHANGED_OBSERVATION'
        changed[-1]['request_messages']=copy.deepcopy(changed[-1]['provider_payload']['messages'])
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):
            c.encode_multiturn_task(self.tok,changed)
        changed=copy.deepcopy(calls)
        changed[-1]['provider_payload']['tools'][0]['function']['description']='CHANGED_SCHEMA'
        with self.assertRaisesRegex(ValueError,'CONTEXT_CHANGED'):
            c.encode_multiturn_task(self.tok,changed)

    def test_empty_thinking_task_requires_decision_segmentation(self):
        messages = self.batch()
        messages[-1].pop('reasoning_content')
        calls = self.task_calls(messages)
        with self.assertRaisesRegex(ValueError, 'REQUIRES_DECISION_SEGMENTATION'):
            c.encode_multiturn_task(self.tok, calls)

    def test_task_rejects_missing_or_duplicate_decisions_and_overflow(self):
        calls=self.task_calls(self.batch())
        with self.assertRaisesRegex(ValueError,'decision count'):
            c.encode_multiturn_task(self.tok,calls[1:])
        with self.assertRaisesRegex(ValueError,'duplicate decision'):
            c.encode_multiturn_task(self.tok,[calls[0],calls[0]])
        with self.assertRaisesRegex(ValueError,'EXCEEDS_CUTOFF_NO_TRUNCATION'):
            c.encode_multiturn_task(self.tok,calls,cutoff=1)


if __name__=='__main__':unittest.main(verbosity=2)
