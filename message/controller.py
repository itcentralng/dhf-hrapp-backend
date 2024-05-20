from fastapi import APIRouter
from fastapi import HTTPException, Depends, Response
from user import utils as user_utils
from message import utils, schema, model
from config import security
from sqlalchemy.orm import Session
from config.database import SessionLocal
import json
from helpers.upload_helper import do_upload

from fastapi import Form, UploadFile
from typing import Annotated, List

router = APIRouter()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post('/upload-document/')
async def upload_document(document: UploadFile, 
                          title: Annotated[str, Form()], 
                          label: Annotated[str, Form()],
                          recipients: Annotated[List[str], Form()],
                          text: Annotated[str, Form()]=None,
                          db: Session = Depends(get_db), 
                          current_user_id = Depends(security.get_current_user)
                          ):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        
        if document is None:
            raise HTTPException(status_code=400, detail=json.dumps({'message':'No document to upload'}))

        #upload document first
        doc_url = do_upload(document, user.email)

        #store details in db
        message_data = {'sender_id':user.id,
                        'label':label,
                        'title':title,
                        'document':doc_url,
                        'text':text,
                        'type':'document_upload',
                        'status':'doc_upload'}
        message_schema = schema.CreateMessage(**message_data)

        db_message = utils.create_message(message=message_schema, recipients=recipients, db=db)

        #TODO: send notification to recipient ...
        return Response(status_code=200, content=json.dumps({'message':'Document sent successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))


@router.get('/outbox/')
async def get_messages(db: Session = Depends(get_db), current_user_id = Depends(security.get_current_user)):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)

        messages = user.sent_messages
        return_messsages = [schema.ReturnMessage.to_dict(msg=msg, comments=msg.comments, db=db).model_dump() for msg in messages]

        return Response(status_code=200, content=json.dumps(return_messsages))
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

@router.get('/inbox/')
async def get_messages(db: Session = Depends(get_db), current_user_id = Depends(security.get_current_user)):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)

        messages = user.received_messages
        return_messsages = [schema.ReturnMessage.to_dict(msg=msg, comments=msg.comments, db=db).model_dump() for msg in messages]

        return Response(status_code=200, content=json.dumps(return_messsages))
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

#comment on a message
@router.post('/comment/')
async def comment(comment: schema.CreateComment,
                  db: Session = Depends(get_db), 
                  current_user_id = Depends(security.get_current_user)):
    
    try:
        user = user_utils.get_user(user_id=current_user_id.id, db=db)

        message = utils.get_message(db=db, message_id=comment.message_id)
        
        db_comment = utils.create_comment(db=db, comment=comment, sender_id=user.id)

        #TODO: send notification to recipient ...
        return Response(status_code=200, content=json.dumps({'message':'Comment sent successfully'}))
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))
    

#status update on leave request
@router.put('/respond-to-leave-request')
async def respond_to_leave_request(leave_res: schema.LeaveResponse,
                                   db: Session = Depends(get_db), 
                                   current_user_id = Depends(security.get_current_user)):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        message = utils.get_message(db=db, message_id=leave_res.message_id)

        if user.role.name != 'admin':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized to respond to leave. Must be an admin'}))
        
        if message.status != 'pending':
            raise HTTPException(status_code=400, detail=json.dumps({'message':'Leave request is not pending'}))
        
        if user not in message.recipients:
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Not the recipient of the request'}))
        
        if (leave_res.status == 'approve') or (leave_res.status == 'disapprove') or (leave_res.status == 'approve-without-pay'):
            message.status = leave_res.status
            db.commit()
            db.refresh(message)

            #TODO: send notification to request sender

            return Response(status_code=200, content=json.dumps(schema.ReturnMessage.to_dict(msg=message, comments=message.comments, db=db).model_dump()))
        else:
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Invalid status response'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

@router.get('/view-all-leave-requests')
async def view_all_leave_requests(db: Session = Depends(get_db), 
                                  current_user_id = Depends(security.get_current_user)):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)

        if user.role.name != 'hr':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be hr'}))
            
        leave_requests = utils.get_leave_requests(db=db)
        return_messsages = [schema.ReturnMessage.to_dict(msg=msg, comments=msg.comments, db=db).model_dump() for msg in leave_requests]

        return Response(status_code=200, content=json.dumps(return_messsages))
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))
    
# share leave request with next office (head of section)
@router.post('/share-leave-request')
async def share_leave_request_with_next_office(
    share_leave_request: schema.ShareLeaveRequest,
    db: Session = Depends(get_db), 
    current_user_id = Depends(security.get_current_user)):
    #assuming that the leave request would be forwarded to an admin or all the admin
    try:

        user = user_utils.get_user(db=db, user_id=current_user_id.id)

        if user.role.name != 'hos':
            raise HTTPException(status_code=401, detail="Not authorized to share leave request. must be head of section")
        
        db_message = utils.get_message(db=db, message_id=share_leave_request.message_id)
        
        for recipient in share_leave_request.recipients:
            db_message.recipients.append(user_utils.get_user_by_email(email=recipient, db=db))
        
        db.commit()
        db.refresh(db_message)

        #TODO: send notification to recipient ...
        return Response(status_code=200, content=json.dumps({'message':'Message shared successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

# EVALUATION

@router.post('/perform-evaluation')
async def perform_evaluation(
    evaluation: schema.EvaluationCreate,
    db: Session = Depends(get_db), 
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'hos':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be head of section'}))
        
        db_evaluation = utils.create_evaluation_with_grade(db=db, evaluation=evaluation)       

        #TODO: send notification to admin and hr ...
        return Response(status_code=200, content=json.dumps({'message':'Evaluation Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

@router.get('/evaluations')
async def get_evaluations(
    db: Session = Depends(get_db), 
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name not in ['hr', 'admin']:
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be hr or admin'}))
        
        evaluations = utils.get_all_evaluations(db=db)
        return_evaluations = list()

        for eval in evaluations:
            grade = eval.grade.__dict__
            del grade['_sa_instance_state']
            del grade['created_at']
            del grade['updated_at']

            eval_dict = eval.__dict__
            del eval_dict['_sa_instance_state']
            eval_dict['created_at'] = eval_dict['created_at'].isoformat()
            eval_dict['updated_at'] = eval_dict['updated_at'].isoformat()
            eval_dict['grade'] = grade
            return_evaluations.append(eval_dict)
        
        return Response(status_code=200, content=json.dumps(return_evaluations))
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occured', 'error': str(e)}))

# EARLY CLOSURE

@router.post('/submit-early-closure')
async def submit_early_closure(
    early_closure_data: schema.EarlyClosureCreate,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'staff':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be a teacher'}))

        # Create Early Closure record in the database
        db_early_closure = utils.create_early_closure(db=db, early_closure_data=early_closure_data)

        # TODO: Send notification to HOS
        return Response(status_code=200, content=json.dumps({'message':'Early Closure Submitted Successfully'}))
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-early-closure/{early_closure_id}/hos')
async def respond_early_closure_hos(
    early_closure_id: int,
    response_data: schema.EarlyClosureHOSResponse,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'hos':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be head of section'}))
        
        # Update Early Closure record with HOS response
        utils.update_early_closure_hos_response(db=db, early_closure_id=early_closure_id, response_data=response_data)

        # TODO: Send notification to HR
        return Response(status_code=200, content=json.dumps({'message':'HOS Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-early-closure/{early_closure_id}/hr')
async def respond_early_closure_hr(
    early_closure_id: int,
    response_data: schema.EarlyClosureHRResponse,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'hr':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be HR'}))

        # Update Early Closure record with HR response
        utils.update_early_closure_hr_response(db=db, early_closure_id=early_closure_id, response_data=response_data)

        # TODO: Send notification to Director
        return Response(status_code=200, content=json.dumps({'message':'HR Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-early-closure/{early_closure_id}/director')
async def respond_early_closure_director(
    early_closure_id: int,
    response_data: schema.EarlyClosureDirectorResponse,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'admin':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be Director'}))

        # Update Early Closure record with Director response
        utils.update_early_closure_director_response(db=db, early_closure_id=early_closure_id, response_data=response_data)

        # TODO: Notify user or take any other necessary action
        return Response(status_code=200, content=json.dumps({'message':'Director Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))
    

# STUDY LEAVE

@router.post('/submit-study-leave')
async def submit_study_leave(
    study_leave_data: schema.StudyLeaveApplicant,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'staff':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be a staff'}))

        # Create Study Leave record in the database
        db_study_leave = utils.create_study_leave(db=db, study_leave_data=study_leave_data)

        # TODO: Send notification to Head Teacher
        return Response(status_code=200, content=json.dumps({'message':'Study Leave Application Submitted Successfully'}))
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-study-leave/{study_leave_id}/hos')
async def respond_study_leave_head_teacher(
    study_leave_id: int,
    response_data: schema.StudyLeaveHeadTeacher,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'hos':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be a head teacher'}))
        
        # Update Study Leave record with Head Teacher's response
        utils.update_study_leave_head_teacher_response(db=db, study_leave_id=study_leave_id, response_data=response_data)

        # TODO: Send notification to Accountant
        return Response(status_code=200, content=json.dumps({'message':'Head Teacher Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-study-leave/{study_leave_id}/accountant')
async def respond_study_leave_accountant(
    study_leave_id: int,
    response_data: schema.StudyLeaveAccountant,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'admin':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be an accountant'}))

        # Update Study Leave record with Accountant's response
        utils.update_study_leave_accountant_response(db=db, study_leave_id=study_leave_id, response_data=response_data)

        # TODO: Send notification to HR
        return Response(status_code=200, content=json.dumps({'message':'Accountant Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-study-leave/{study_leave_id}/hr')
async def respond_study_leave_hr(
    study_leave_id: int,
    response_data: schema.StudyLeaveHR,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'hr':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be HR'}))

        # Update Study Leave record with HR's response
        utils.update_study_leave_hr_response(db=db, study_leave_id=study_leave_id, response_data=response_data)

        # TODO: Send notification to Director
        return Response(status_code=200, content=json.dumps({'message':'HR Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))


@router.put('/respond-study-leave/{study_leave_id}/director')
async def respond_study_leave_director(
    study_leave_id: int,
    response_data: schema.StudyLeaveDirector,
    db: Session = Depends(get_db),
    current_user_id = Depends(security.get_current_user)
):
    try:
        user = user_utils.get_user(db=db, user_id=current_user_id.id)
        if user.role.name != 'admin':
            raise HTTPException(status_code=401, detail=json.dumps({'message':'Unauthorized. Must be Director'}))

        # Update Study Leave record with Director's response
        utils.update_study_leave_director_response(db=db, study_leave_id=study_leave_id, response_data=response_data)

        # TODO: Notify user or take any other necessary action
        return Response(status_code=200, content=json.dumps({'message':'Director Response Submitted Successfully'}))

    except Exception as e:
        raise HTTPException(status_code=400, detail=json.dumps({'message':'An Error Occurred', 'error': str(e)}))
