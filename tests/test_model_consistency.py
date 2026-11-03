from zonesim.combat.loot import Corpse as CombatCorpse
from zonesim.monsters.behavior import Monster as BehaviorMonster
from zonesim.monsters.feed import Corpse as FeedCorpse
from zonesim.news.events import NewsManager as EventNewsManager
from zonesim.news.events import WorldEvent as EventWorldEvent
from zonesim.relations.news import NewsManager, WorldEvent
from zonesim.world.entity import Monster


def test_corpse_model_is_shared():
    assert FeedCorpse is CombatCorpse


def test_monster_model_is_shared():
    assert BehaviorMonster is Monster


def test_news_models_are_shared():
    assert EventWorldEvent is WorldEvent
    assert EventNewsManager is NewsManager
