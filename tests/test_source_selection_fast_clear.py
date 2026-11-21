"""Source isolation with NotebookLM's default all-selected checkbox."""
import unittest
from unittest.mock import AsyncMock
from app.services.notebooklm_page import NotebookLMPageClient


class Checkbox:
    def __init__(self, group, index):self.group,self.index=group,index
    async def wait_for(self,**kwargs):pass
    async def is_checked(self):
        return all(self.group.states) if self.index==0 else self.group.states[self.index-1]
    async def evaluate(self,script):
        if ".click()" not in script:return self.group.labels[self.index]
        if "querySelector('label')" not in script:
            raise AssertionError('Activate the real label, not the outer checkbox host')
        self.group.clicks.append(self.index)
        if self.index==0:
            self.group.states[:]=[not all(self.group.states)]*len(self.group.states)
        else:self.group.states[self.index-1]=not self.group.states[self.index-1]


class Checkboxes:
    def __init__(self,states):
        self.labels=['Select all','36 00_00_00-02_30_00.mp3','36 02_30_00-05_03_00.mp3','35.mp3']
        self.states=list(states);self.clicks=[]
    @property
    def first(self):return self.nth(0)
    def nth(self,index):return Checkbox(self,index)
    async def count(self):return len(self.labels)


class SourceSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def run_selection(self,states,target,book=None):
        boxes=Checkboxes(states)
        page=AsyncMock();page.locator=lambda _:boxes
        client=NotebookLMPageClient.__new__(NotebookLMPageClient)
        await client.select_source(page,target,book)
        return boxes
    async def test_default_all_uses_two_clicks(self):
        boxes=await self.run_selection([True,True,True],'36 00_00_00-02_30_00.mp3')
        self.assertEqual(boxes.states,[True,False,False]);self.assertEqual(boxes.clicks,[0,1])
    async def test_mixed_does_not_toggle_select_all(self):
        boxes=await self.run_selection([False,True,False],'36 00_00_00-02_30_00.mp3')
        self.assertEqual(boxes.states,[True,False,False]);self.assertNotIn(0,boxes.clicks)
    async def test_all_prefix_keeps_both_requested_parts(self):
        boxes=await self.run_selection([True,True,True],'ALL:36')
        self.assertEqual(boxes.states,[True,True,False]);self.assertEqual(boxes.clicks,[0,1,2])
    async def test_missing_target_does_not_change_selection(self):
        with self.assertRaises(RuntimeError):await self.run_selection([True,True,True],'missing.mp3')


if __name__=='__main__':unittest.main()
