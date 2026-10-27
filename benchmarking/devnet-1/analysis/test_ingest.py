import hashlib
import unittest
from collections import defaultdict
from ingest import Reducer, GENESIS, parse, line_time, select_sources, slot_profile_interval


class IngestionTests(unittest.TestCase):
    def reducer(self):
        return Reducer({'name':'test','chain':0,'node':1,'owned_slots':[10,11],'sha256':hashlib.sha256(b'').hexdigest()})

    def test_native_and_slog_clocks(self):
        a=line_time(b'[2026-10-08 15:55:30.03]  INFO sync: FFG vote')
        b=line_time(b'time=2026-10-08T15:55:30.030Z level=INFO')
        self.assertEqual(a,b)

    def test_multiseat_queue_is_one_message_and_one_acceptance(self):
        r=self.reducer()
        f={'voteSlot':'10','blockRoot':'0xabc','validator':'9','seats':'2','outcome':'queued','arrivedMs':'500','decidedMs':'505'}
        r.event(GENESIS[0]+120000+505,'Goldfish vote',f)
        r.event(GENESIS[0]+120000+901,'Goldfish vote',dict(f,outcome='replayed',arrivedMs='890',decidedMs='901'))
        d=r.finish()
        self.assertEqual(d['audit']['observed_events'],1)
        self.assertEqual(d['audit']['accepted_events'],1)
        self.assertEqual(d['events'][0][2],5)
        self.assertEqual(d['events'][1][2],9)
        self.assertEqual(d['events'][0][7],2)

    def test_explicit_ffg_decision_and_bundle(self):
        r=self.reducer()
        f={'attSlot':'10','arrivedMs':'1100','decidedMs':'1120','outcome':'gossip','transport':'bundle','seats':'1'}
        r.event(GENESIS[0]+120000+1190,'FFG vote',f)
        self.assertEqual(r.delays[(10,1)][20],1)
        self.assertEqual(r.audit['explicit_decision_events'],1)

    def test_ignored_aggregates_are_not_accepted(self):
        r=self.reducer()
        r.event(GENESIS[0]+120000+9000,'FFG aggregate',{'attSlot':'10','arrivedMs':'9000','outcome':'ignored','seats':'2000','committeeIndex':'1','reason':'already_known'})
        self.assertEqual(r.audit['accepted_events'],0)
        self.assertEqual(r.audit['ignored_aggregate_events'],1)

    def test_rpc_intervals_conserve_bytes_across_slot_boundary(self):
        rows=defaultdict(lambda:[0.0])
        slot_profile_interval(GENESIS[0]+12050,200,[1000],{0,1},GENESIS[0],rows,('all','recv'))
        self.assertAlmostEqual(sum(v[0] for v in rows.values()),1000)
        self.assertAlmostEqual(rows[(1,0,'all','recv')][0],250)

    def test_partial_subsets_are_not_added_twice(self):
        r=self.reducer()
        f={'interval_ms':'100'}
        for d in ['recv','send','drop']:
            f.update({d+'_bytes':'100',d+'_partial_bytes':'80',d+'_overhead_bytes':'20',d+'_pm_total_bytes':'80',d+'_pm_message_bytes':'60'})
        r.bandwidth(GENESIS[0]+120100,f)
        self.assertEqual(r.network[(10,0,'all','recv')][0],100)
        self.assertEqual(r.network[(10,0,'all','recv')][2],80)

    def test_source_overlap_has_unique_owner(self):
        prefix='dc-devnet-1-logs/'
        def source(name,lo,hi):
            return {'name':prefix+name+'/prysm-geth-1/beacon.log','first':lo,'last':hi,'sha256':'test','expanded_bytes':1}
        selected=select_sources({'members':[
            source('full-a','2026-10-08T15:30:05Z','2026-10-08T15:31:05Z'),
            source('full-b','2026-10-08T15:30:29Z','2026-10-08T15:31:29Z')]})
        slots=[s for x in selected.values() for s in x['owned_slots']]
        self.assertEqual(len(slots),len(set(slots)))
        self.assertEqual(set(slots),set(range(7)))

    def test_field_lists_and_quoted_slog(self):
        msg,f,_=parse(b'[2026-10-08 15:55:30.03] INFO sync: FFG aggregate validators=[1 2 3] seats=3')
        self.assertEqual(f['validators'],'[1 2 3]')
        msg,f,_=parse(b'time=2026-10-08T15:55:30.03Z level=INFO msg="gossipsub topic bandwidth" topic="" bytes=0')
        self.assertEqual(f['topic'],'')
        self.assertEqual(msg,'gossipsub topic bandwidth')

    def test_special_start_capture_is_not_throttled_export(self):
        s={'name':'dc-devnet-1-logs/node-355-start-1646/beacon.log.gz','first':'2026-10-08T15:30:05Z','last':'2026-10-08T15:31:05Z','sha256':'x','expanded_bytes':1}
        selected=select_sources({'members':[s]})
        self.assertEqual(next(iter(selected.values()))['node'],355)


if __name__=='__main__':unittest.main()
