import datetime
from typing import List, Tuple, Union, Optional

def datetime_to_timestamp(dt: datetime.datetime):
  return int(dt.timestamp())

def rank_dinkdonks(dd_list: List[Tuple[str, int]], cut_off_at_length: Optional[int]=None, cut_off_at_user_id: Union[str, int, None]=None) -> List[Tuple[int, List[str]]]:
  if len(dd_list) == 0:
    return []
  if type(cut_off_at_user_id) is int:
    cut_off_at_user_id = str(cut_off_at_user_id)
  dd_list = sorted(dd_list, key=lambda v: v[1], reverse=True)
  current_users = [dd_list[0][0]]
  current_score = dd_list[0][1]
  ranked_dd_list = [(current_score, current_users)]
  if cut_off_at_user_id and current_users[0] == cut_off_at_user_id:
    return ranked_dd_list
  for dd in dd_list[1:]:
    if dd[1] < current_score:
      if cut_off_at_length and len(ranked_dd_list) >= cut_off_at_length:
        break
      current_users = [dd[0]]
      current_score = dd[1]
      ranked_dd_list.append((current_score, current_users))
    else:
      current_users.append(dd[0])
    if cut_off_at_user_id and dd[0] == cut_off_at_user_id:
      break
  return ranked_dd_list

def get_ordinal(number: int):
  lastdigit = abs(number) % 10
  last2 = abs(number) % 100
  if 10 < last2 <= 13:
    return f'{number}th'
  if lastdigit == 1:
    return f'{number}st'
  if lastdigit == 2:
    return f'{number}nd'
  if lastdigit == 3:
    return f'{number}rd'
  return f'{number}th'
